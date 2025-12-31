import os
from fastapi import FastAPI, UploadFile, File, Form, Request, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import shutil
import pandas as pd
import io
import traceback
import uuid

# App Imports
from app.services.data_processing import AndreaniProcessor
from app.services.pdf_processing import process_pdf_labels, construir_mapa_skus
from app.services.tiendanube import TiendaNubeAuth, TiendaNubeClient
from app.services.csv_generator import TiendaNubeCSVGenerator
from app.database import init_db
from fastapi.responses import RedirectResponse

app = FastAPI(title="Andreani Automation Web App")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Config paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANDREANI_TEMPLATE = os.path.join(BASE_DIR, "EnvioMasivoExcelPaquetes.xlsx")
# Output configs - These might need to be temp dirs in production!
# For Render, writable disk is ephemeral usually, but okay for tmp files.
OUTPUT_EXCEL = "/tmp/EnvioMasivoExcelPaquetes_cargado.xlsx"
OUTPUT_PDF = "/tmp/documentos_combinados_con_sku.pdf"

# Ensure /tmp exists on Windows (locally)
if os.name == 'nt':
    OUTPUT_EXCEL = os.path.join(BASE_DIR, "temp_output_excel.xlsx")
    OUTPUT_PDF = os.path.join(BASE_DIR, "temp_output_pdf.pdf")

# Data Processor Instance
# Singleton is fine
processor = AndreaniProcessor(ANDREANI_TEMPLATE)

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/excel", response_class=HTMLResponse)
async def view_excel_process(request: Request):
    return templates.TemplateResponse("excel_process.html", {"request": request})

@app.get("/pdf", response_class=HTMLResponse)
async def view_pdf_process(request: Request):
    return templates.TemplateResponse("pdf_process.html", {"request": request})

@app.post("/api/parse-csv")
async def parse_csv(file: UploadFile = File(...)):
    try:
        content = await file.read()
        results = processor.process_csv(content)
        if isinstance(results, dict) and "error" in results:
            return JSONResponse(status_code=400, content=results)
        return results
    except Exception as e:
        print(f"Error parsing CSV: {e}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/generate-excel")
async def generate_excel(data: dict):
    # data expects {"records": [...]}
    records = data.get("records", [])
    if not records:
        return JSONResponse(status_code=400, content={"error": "No records provided"})
    
    try:
        output_path = processor.generate_excel(records, OUTPUT_EXCEL)
        return FileResponse(
            output_path, 
            filename="EnvioMasivoExcelPaquetes_cargado.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/process-pdf")
async def process_pdf(
    pdf_file: UploadFile = File(...),
    csv_file: UploadFile = File(...)
):
    try:
        pdf_bytes = await pdf_file.read()
        csv_bytes = await csv_file.read()
        
        skus_map = construir_mapa_skus(csv_bytes)
        modified_pdf = process_pdf_labels(pdf_bytes, skus_map)
        
        # Save temporarily
        with open(OUTPUT_PDF, "wb") as f:
            f.write(modified_pdf)
            
        return FileResponse(OUTPUT_PDF, filename="Etiquetas_Con_SKU.pdf", media_type="application/pdf")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# --- Tienda Nube Routes ---

@app.get("/tracking", response_class=HTMLResponse)
async def view_tracking_process(request: Request):
    token_data = TiendaNubeAuth.get_valid_token()
    is_authenticated = token_data is not None
    return templates.TemplateResponse("tracking_process.html", {
        "request": request,
        "is_authenticated": is_authenticated
    })

@app.get("/tiendanube/login")
async def tiendanube_login():
    auth_url = TiendaNubeAuth.get_auth_url()
    return RedirectResponse(auth_url)

@app.get("/tiendanube/callback")
async def tiendanube_callback(request: Request, code: str):
    print(f"CALLBACK HIT {request.url} code={code}")
    try:
        TiendaNubeAuth.exchange_code_for_token(code)
        return RedirectResponse(url="/tracking")
    except Exception as e:
        print(f"Callback Error: {e}")
        return JSONResponse(status_code=400, content={"error": f"Auth failed: {str(e)}"})

@app.post("/api/update-tracking")
async def update_tracking_codes(file: UploadFile = File(...)):
    token_data = TiendaNubeAuth.get_valid_token()
    if not token_data:
        return JSONResponse(status_code=401, content={"error": "Not authenticated. Please login first."})
    
    try:
        content = await file.read()
        
        store_id = token_data.get("user_id")
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise RuntimeError("Missing access_token")
        
        client = TiendaNubeClient(store_id=store_id, access_token=access_token)
        result = client.process_tracking_file(content)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/orders-ready", response_class=HTMLResponse)
async def view_orders_ready(request: Request):
    token_data = TiendaNubeAuth.get_valid_token()
    if not token_data:
        return RedirectResponse("/tiendanube/login")
    return templates.TemplateResponse("orders_ready.html", {"request": request})

@app.get("/api/orders/ready")
async def api_list_orders_ready(page: int = 1, per_page: int = 20, q: str = None, stage: str = None, debug: bool = False):
    try:
        token_data = TiendaNubeAuth.get_valid_token()
        if not token_data or not token_data.get("access_token"):
             logger_error_msg = "Re-connect the app (missing access_token)"
             print(f"ERROR: {logger_error_msg}")
             return JSONResponse(status_code=401, content={
                 "ok": False,
                 "error": logger_error_msg
             })
        
        client = TiendaNubeClient(token_data.get("user_id"), token_data.get("access_token"))
        statuses = ["paid"]
        ret_data = client.list_orders_ready(page=page, per_page=per_page, q=q, payment_statuses=statuses, stage=stage, debug=debug)
        
        return {
            "ok": True, 
            "results": ret_data["results"], 
            "debug": ret_data.get("debug", [])
        }

    except Exception as e:
        err_str = str(e)
        tb_str = traceback.format_exc()
        print(f"CRITICAL ERROR in /orders/ready:\n{tb_str}")
        return JSONResponse(status_code=500, content={
            "ok": False, 
            "error": err_str,
            "traceback": tb_str
        })

@app.get("/api/orders/stats")
async def api_orders_stats():
    token_data = TiendaNubeAuth.get_valid_token()
    if not token_data or not token_data.get("access_token"):
        return {"ok": False, "stats": {"unpacked": 0, "packed": 0}}
        
    try:
        client = TiendaNubeClient(token_data.get("user_id"), token_data.get("access_token"))
        stats = client.get_order_stats()
        return {"ok": True, "stats": stats}
    except Exception as e:
        print(f"Stats Error: {e}")
        return {"ok": False, "stats": {"unpacked": 0, "packed": 0}}


@app.post("/andreani/csv")
async def generate_andreani_csv_route(data: dict):
    nums = data.get("order_numbers", [])
    if not nums:
        return JSONResponse(status_code=400, content={"error": "No orders selected"})
    
    token_data = TiendaNubeAuth.get_valid_token()
    if not token_data or not token_data.get("access_token"):
         return JSONResponse(status_code=401, content={"error": "Not authenticated"})
    
    try:
        client = TiendaNubeClient(token_data.get("user_id"), token_data.get("access_token"))
        
        full_orders = []
        errors = []
        
        for num in nums:
            try:
                real_id = client.lookup_real_order_id(num)
                order = client.get_order(real_id)
                full_orders.append(order)
            except Exception as e:
                print(f"Error preparing CSV for order {num}: {e}")
                errors.append(f"Order {num}: {str(e)}")

        if not full_orders and errors:
             return JSONResponse(status_code=400, content={"error": f"Failed to fetch orders: {'; '.join(errors)}"})

        csv_bytes = TiendaNubeCSVGenerator.generate(full_orders)
        
        return StreamingResponse(
            io.BytesIO(csv_bytes), 
            media_type="text/csv", 
            headers={"Content-Disposition": "attachment; filename=ventas_andreani_gen.csv"}
        )

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

# Batch Process
BATCH_STORE = {}

@app.post("/api/orders/process-batch")
async def process_batch_route(data: dict):
    nums = data.get("order_numbers", [])
    if not nums:
        return JSONResponse(status_code=400, content={"error": "No orders selected"})
    
    token_data = TiendaNubeAuth.get_valid_token()
    if not token_data or not token_data.get("access_token"):
         return JSONResponse(status_code=401, content={"error": "Not authenticated"})
    
    try:
        client = TiendaNubeClient(token_data.get("user_id"), token_data.get("access_token"))
        
        full_orders = []
        errors = []
        
        for num in nums:
            try:
                real_id = client.lookup_real_order_id(num)
                order = client.get_order(real_id)
                full_orders.append(order)
            except Exception as e:
                print(f"Error for batch {num}: {e}")
                errors.append(f"Order {num}: {str(e)}")

        if not full_orders and errors:
             return JSONResponse(status_code=400, content={"error": f"Failed to fetch orders: {'; '.join(errors)}"})

        csv_bytes = TiendaNubeCSVGenerator.generate(full_orders)
        
        # Processor used here
        results = processor.process_csv(csv_bytes)
        
        if isinstance(results, dict) and "error" in results:
             return JSONResponse(status_code=400, content=results)

        batch_id = str(uuid.uuid4())
        BATCH_STORE[batch_id] = results
        
        return {
            "ok": True,
            "batch_id": batch_id,
            "redirect_url": f"/excel?batch_id={batch_id}"
        }

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/batch/{batch_id}")
async def get_batch_data(batch_id: str):
    data = BATCH_STORE.get(batch_id)
    if not data:
        return JSONResponse(status_code=404, content={"error": "Batch not found or expired"})
    return data
