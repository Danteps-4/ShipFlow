import os
from fastapi import FastAPI, UploadFile, File, Form, Request, Depends, HTTPException, status
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
from datetime import timedelta

# App Imports
from app.services.data_processing import AndreaniProcessor
from app.services.pdf_processing import process_pdf_labels, construir_mapa_skus
from app.services.tiendanube import TiendaNubeAuth, TiendaNubeClient
from app.services.csv_generator import TiendaNubeCSVGenerator
from app.database import init_db, get_session
from app.dependencies import get_current_store_id, get_current_store
from app.models import Store
from sqlmodel import select, Session

from fastapi.responses import RedirectResponse, Response

app = FastAPI(title="Andreani Automation Web App")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Config paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANDREANI_TEMPLATE = os.path.join(BASE_DIR, "EnvioMasivoExcelPaquetes.xlsx")
# Output configs
OUTPUT_EXCEL = "/tmp/EnvioMasivoExcelPaquetes_cargado.xlsx"
OUTPUT_PDF = "/tmp/documentos_combinados_con_sku.pdf"

if os.name == 'nt':
    OUTPUT_EXCEL = os.path.join(BASE_DIR, "temp_output_excel.xlsx")
    OUTPUT_PDF = os.path.join(BASE_DIR, "temp_output_pdf.pdf")

processor = AndreaniProcessor(ANDREANI_TEMPLATE)

# --- Auth Routes ---
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordRequestForm
from app.models import User
from app.security import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.dependencies import get_current_user

class UserCreate(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

@app.post("/auth/register", response_model=Token)
async def register(user_in: UserCreate, session: Session = Depends(get_session)):
    if len(user_in.password) < 8 or len(user_in.password) > 256:
        raise HTTPException(status_code=400, detail="Password must be between 8 and 256 characters")

    # Check if exists
    existing = session.exec(select(User).where(User.email == user_in.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = User(
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        is_admin=False # Default
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    
    # Login immediately
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    # Note: OAuth2PasswordRequestForm expects "username", we use "email"
    user = session.exec(select(User).where(User.email == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "is_admin": current_user.is_admin
    }

@app.on_event("startup")
def on_startup():
    init_db()

# --- Common Context ---
# We can inject 'stores' list into templates globally or per request
def get_user_stores(session: Session = next(get_session())):
    # Quick helper for admin user 1 (Sprint 2 assumption)
    return session.exec(select(Store).where(Store.user_id == 1)).all()

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
        
        with open(OUTPUT_PDF, "wb") as f:
            f.write(modified_pdf)
            
        return FileResponse(OUTPUT_PDF, filename="Etiquetas_Con_SKU.pdf", media_type="application/pdf")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# --- Tienda Nube Multi-Store Routes ---

@app.get("/settings", response_class=HTMLResponse)
async def view_settings(request: Request, session: Session = Depends(get_session)):
    # List all stores for admin
    stores = session.exec(select(Store).where(Store.user_id == 1)).all()
    return templates.TemplateResponse("settings.html", {"request": request, "stores": stores})

@app.get("/tracking", response_class=HTMLResponse)
async def view_tracking_process(request: Request, store_id: int = Depends(get_current_store_id)):
    token_data = TiendaNubeAuth.get_valid_token(store_id)
    is_authenticated = token_data is not None
    return templates.TemplateResponse("tracking_process.html", {
        "request": request,
        "is_authenticated": is_authenticated,
        "active_store_id": store_id
    })

@app.get("/tiendanube/connect")
async def tiendanube_connect(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    auth_url = TiendaNubeAuth.get_auth_url(current_user.id, session)
    return RedirectResponse(auth_url)

@app.get("/tiendanube/callback")
async def tiendanube_callback(request: Request, code: str, state: str, session: Session = Depends(get_session)):
    print(f"CALLBACK HIT {request.url} code={code} state={state}")
    try:
        # Process Callback (validates state, links user, returns store info)
        token_data_full = TiendaNubeAuth.process_callback(code, state, session)
        store_id = token_data_full.get("store_id")
        
        # Set cookie and redirect
        response = RedirectResponse(url="/settings") # Go to settings
        response.set_cookie(key="andreani_active_store", value=str(store_id))
        return response
    except Exception as e:
        print(f"Callback Error: {e}")
        return JSONResponse(status_code=400, content={"error": f"Auth failed: {str(e)}"})

# Endpoint to switch active store manually
@app.post("/api/set-active-store")
async def set_active_store(data: dict):
    store_id = data.get("store_id")
    response = JSONResponse({"ok": True, "store_id": store_id})
    response.set_cookie(key="andreani_active_store", value=str(store_id))
    return response

@app.get("/api/me/stores")
async def get_my_stores(session: Session = Depends(get_session)):
    # Return list of stores for frontend selector
    # Sprint 2: Hardcoded user_id=1
    stores = session.exec(select(Store).where(Store.user_id == 1)).all()
    return [
        {"id": s.id, "name": s.name, "tiendanube_user_id": s.tiendanube_user_id}
        for s in stores
    ]


@app.post("/api/update-tracking")
async def update_tracking_codes(file: UploadFile = File(...), store_id: int = Depends(get_current_store_id)):
    token_data = TiendaNubeAuth.get_valid_token(store_id)
    if not token_data:
        return JSONResponse(status_code=401, content={"error": "Not authenticated or no active store selected."})
    
    try:
        content = await file.read()
        
        store_id_tn = token_data.get("user_id") # TN Store ID
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise RuntimeError("Missing access_token")
        
        client = TiendaNubeClient(store_id=store_id_tn, access_token=access_token)
        result = client.process_tracking_file(content)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/orders-ready", response_class=HTMLResponse)
async def view_orders_ready(request: Request, store_id: int = Depends(get_current_store_id)):
    token_data = TiendaNubeAuth.get_valid_token(store_id)
    if not token_data:
        # If no store active, maybe redirect to settings to select one?
        return RedirectResponse("/settings")
    return templates.TemplateResponse("orders_ready.html", {
        "request": request,
        "active_store_id": store_id
    })

@app.get("/api/orders/ready")
async def api_list_orders_ready(
    page: int = 1, 
    per_page: int = 50, 
    q: str = None, 
    stage: str = None, 
    debug: bool = False,
    store_id: int = Depends(get_current_store_id)
):
    try:
        token_data = TiendaNubeAuth.get_valid_token(store_id)
        if not token_data:
             return JSONResponse(status_code=401, content={
                 "ok": False,
                 "error": "No active store or not authenticated"
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
        tb_str = traceback.format_exc()
        print(f"CRITICAL ERROR in /orders/ready:\n{tb_str}")
        return JSONResponse(status_code=500, content={
            "ok": False, 
            "error": str(e),
            "traceback": tb_str
        })

@app.get("/api/orders/stats")
async def api_orders_stats(store_id: int = Depends(get_current_store_id)):
    token_data = TiendaNubeAuth.get_valid_token(store_id)
    if not token_data:
        return {"ok": False, "stats": {"unpacked": 0, "packed": 0}}
        
    try:
        client = TiendaNubeClient(token_data.get("user_id"), token_data.get("access_token"))
        stats = client.get_order_stats()
        return {"ok": True, "stats": stats}
    except Exception as e:
        print(f"Stats Error: {e}")
        return {"ok": False, "stats": {"unpacked": 0, "packed": 0}}


@app.post("/andreani/csv")
async def generate_andreani_csv_route(data: dict, store_id: int = Depends(get_current_store_id)):
    nums = data.get("order_numbers", [])
    if not nums:
        return JSONResponse(status_code=400, content={"error": "No orders selected"})
    
    token_data = TiendaNubeAuth.get_valid_token(store_id)
    if not token_data:
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
async def process_batch_route(data: dict, store_id: int = Depends(get_current_store_id)):
    nums = data.get("order_numbers", [])
    if not nums:
        return JSONResponse(status_code=400, content={"error": "No orders selected"})
    
    token_data = TiendaNubeAuth.get_valid_token(store_id)
    if not token_data:
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
