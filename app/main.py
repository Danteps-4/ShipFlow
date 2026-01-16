import os
from fastapi import FastAPI, UploadFile, File, Form, Request, Depends, HTTPException, status, Body
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse, RedirectResponse, Response
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
from pydantic import BaseModel

# App Imports
from app.services.data_processing import AndreaniProcessor
from app.services.pdf_processing import process_pdf_labels, construir_mapa_skus
from app.services.tiendanube import TiendaNubeAuth, TiendaNubeClient
from app.services.csv_generator import TiendaNubeCSVGenerator
from app.database import init_db, get_session
from app.dependencies import get_current_store_id, get_current_store, get_current_user
from app.models import Store, User
from app.auth import hash_password, verify_password, create_session, delete_session
from app.security import encrypt_token
from sqlmodel import select, Session

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

@app.on_event("startup")
def on_startup():
    init_db()

# --- Common Context ---
def get_user_stores(user: User, session: Session):
    return session.exec(select(Store).where(Store.user_id == user.id)).all()

# --- Public & UI Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # Optional: if logged in, show dashboard/home, else maybe landing?
    # For now keep it simple.
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/logout")
async def logout(request: Request, session: Session = Depends(get_session)):
    token = request.cookies.get("session")
    delete_session(session, token)
    response = RedirectResponse(url="/login")
    response.delete_cookie("session")
    response.delete_cookie("andreani_active_store") # Clear active store too
    return response

# --- Auth API ---

class UserAuth(BaseModel):
    email: str
    password: str

@app.post("/auth/register")
async def register(data: UserAuth, session: Session = Depends(get_session)):
    email = data.email.strip().lower()
    
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="El email ya está registrado.")
    
    hashed = hash_password(data.password)
    user = User(email=email, password_hash=hashed)
    session.add(user)
    session.commit()
    session.refresh(user)
    
    # Auto-login
    token = create_session(session, user.id)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="session", 
        value=token, 
        httponly=True, 
        samesite="lax",
        secure=(os.getenv("ENV") == "production")
    )
    return response

@app.post("/auth/login")
async def login(data: UserAuth, session: Session = Depends(get_session)):
    email = data.email.strip().lower()
    user = session.exec(select(User).where(User.email == email)).first()
    
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    
    token = create_session(session, user.id)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="session", 
        value=token, 
        httponly=True, 
        samesite="lax",
        secure=(os.getenv("ENV") == "production")
    )
    return response

@app.get("/auth/register")
async def register_get_redirect():
    return RedirectResponse("/register")

@app.get("/auth/login")
async def login_get_redirect():
    return RedirectResponse("/login")

@app.get("/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "created_at": user.created_at
    }


# --- Protected Routes ---

@app.get("/excel", response_class=HTMLResponse)
async def view_excel_process(
    request: Request, 
    user: User = Depends(get_current_user) # Require login
):
    return templates.TemplateResponse("excel_process.html", {"request": request})

@app.get("/pdf", response_class=HTMLResponse)
async def view_pdf_process(
    request: Request,
    user: User = Depends(get_current_user) # Require login
):
    return templates.TemplateResponse("pdf_process.html", {"request": request})

@app.post("/api/parse-csv")
async def parse_csv(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user) # Require login
):
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
async def generate_excel(
    data: dict,
    user: User = Depends(get_current_user)
):
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
    csv_file: UploadFile = File(...),
    user: User = Depends(get_current_user)
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
async def view_settings(
    request: Request, 
    user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    # Multi-tenant: filter by current_user.id
    stores = session.exec(select(Store).where(Store.user_id == user.id)).all()
    return templates.TemplateResponse("settings.html", {"request": request, "stores": stores})

@app.get("/tracking", response_class=HTMLResponse)
async def view_tracking_process(
    request: Request, 
    store_id: int = Depends(get_current_store_id),
    user: User = Depends(get_current_user) # Redirect to login if needed handled by exception
):
    token_data = TiendaNubeAuth.get_valid_token(store_id)
    is_authenticated = token_data is not None
    return templates.TemplateResponse("tracking_process.html", {
        "request": request,
        "is_authenticated": is_authenticated,
        "active_store_id": store_id
    })

@app.get("/tiendanube/login")
async def tiendanube_login(user: User = Depends(get_current_user)):
    # Note: Tienda Nube callback is public (Redirect URI), so we must persist user session
    # The session cookie handles this automaticlly.
    auth_url = TiendaNubeAuth.get_auth_url()
    return RedirectResponse(auth_url)

@app.get("/tiendanube/callback")
async def tiendanube_callback(
    request: Request, 
    code: str,
    user: User = Depends(get_current_user), # Ensure user is logged in to attach store
    session: Session = Depends(get_session)
):
    print(f"CALLBACK HIT {request.url} code={code}")
    try:
        # Exchange returns dict with "user_id", "access_token", "token_type", "scope"
        token_data = TiendaNubeAuth.exchange_code_for_token(code)
        
        tiendanube_store_id = int(token_data.get("user_id")) # This is TN Store ID
        access_token = token_data.get("access_token")
        token_type = token_data.get("token_type")
        scope = token_data.get("scope")

        # B4) Evitar el caso tiendanube_user_id=1
        if tiendanube_store_id == 1:
            return JSONResponse(status_code=400, content={"error": "ID de tienda inválido (1). Contacte soporte."})
        
        # Link to our local Store model
        # Check if store already exists for this TN ID (Global Unique)
        query = select(Store).where(Store.tiendanube_user_id == tiendanube_store_id)
        existing_store = session.exec(query).first()
        
        store = None
        
        if existing_store:
            # B2) UPSERT Correcto
            # Si existe, actualizamos token y verificamos ownership.
            # En teoría una misma tienda TN no puede ser manejada por 2 usuarios distintos en nuestra APP 
            # (con el modelo actual 1:N User:Store).
            if existing_store.user_id != user.id:
                 # TODO: Decidir política. Opción A: Denegar. Opción B: Robar ownership?
                 # Por seguridad, denegar. El usuario debe contactar soporte si cambió de cuenta.
                 # O quizás es el mismo humano con otro email.
                 return JSONResponse(status_code=400, content={"error": "Esta tienda ya está vinculada a otro usuario de ShipFlow."})
            
            store = existing_store
            print(f"Updating Store {store.id} for TN ID {tiendanube_store_id}")
            # Si quisieramos actualizar nombre, podríamos buscar info de la tienda aquí.
        else:
             # Create new store
             print(f"Creating New Store for TN ID {tiendanube_store_id}")
             store = Store(
                 name=f"Tienda {tiendanube_store_id}",
                 tiendanube_user_id=tiendanube_store_id,
                 user_id=user.id
             )
             session.add(store)
             session.commit()
             session.refresh(store)
        
        # Upsert Token
        from app.security import encrypt_token
        encrypted_token = encrypt_token(access_token)
        
        query_token = select(TiendaNubeToken).where(TiendaNubeToken.store_id == store.id)
        existing_token = session.exec(query_token).first()
        
        if existing_token:
            existing_token.access_token_encrypted = encrypted_token
            existing_token.token_type = token_type
            existing_token.scope = scope
            existing_token.user_id = tiendanube_store_id
            session.add(existing_token)
        else:
            new_token = TiendaNubeToken(
                access_token_encrypted=encrypted_token,
                token_type=token_type,
                scope=scope,
                user_id=tiendanube_store_id,
                store_id=store.id
            )
            session.add(new_token)
            
        session.commit()
        session.refresh(store)
        
        # Set active store
        response = RedirectResponse(url="/settings")
        # B3) Set cookie con ID real
        response.set_cookie(key="andreani_active_store", value=str(store.id))
        return response

    except Exception as e:
        print(f"Callback Error: {e}")
        return JSONResponse(status_code=400, content={"error": f"Auth failed: {str(e)}"})

# Endpoint to switch active store manually
@app.post("/api/set-active-store")
async def set_active_store(
    data: dict,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    store_id = data.get("store_id")
    # Verify ownership
    if not store_id:
        return JSONResponse(status_code=400, content={"error": "Missing store_id"})
        
    store = session.get(Store, store_id)
    if not store or store.user_id != user.id:
        return JSONResponse(status_code=403, content={"error": "Acceso denegado a esta tienda"})
        
    response = JSONResponse({"ok": True, "store_id": store_id})
    response.set_cookie(key="andreani_active_store", value=str(store_id))
    return response

@app.get("/api/me/stores")
async def get_my_stores(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    stores = session.exec(select(Store).where(Store.user_id == user.id)).all()
    return [
        {"id": s.id, "name": s.name, "tiendanube_user_id": s.tiendanube_user_id}
        for s in stores
    ]


@app.post("/api/update-tracking")
async def update_tracking_codes(
    file: UploadFile = File(...), 
    store: Store = Depends(get_current_store), # This checks ownership via get_current_store
    user: User = Depends(get_current_user)
):
    if not store:
        return JSONResponse(status_code=400, content={"error": "No active store selected"})
        
    store_id = store.id
    """
    Starts the batch tracking update process.
    Parses the file and initializes a batch. 
    Returns { "ok": true, "batch_id": "...", "total": N }
    """
    token_data = TiendaNubeAuth.get_valid_token(store_id)
    if not token_data:
        return JSONResponse(status_code=401, content={"error": "Not authenticated with Tienda Nube."})

    try:
        content = await file.read()
        store_id_tn = token_data.get("user_id")
        access_token = token_data.get("access_token")
        client = TiendaNubeClient(store_id=store_id_tn, access_token=access_token)
        
        # Parse only
        items = client.parse_tracking_file(content)
        
        batch_id = str(uuid.uuid4())
        BATCH_TRACKING_STORE[batch_id] = {
            "items": items,
            "total": len(items),
            "processed": 0,
            "results": [],
            "store_id": store_id,
            "client_data": token_data
        }
        
        return {
            "ok": True,
            "batch_id": batch_id,
            "total": len(items)
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# Removed /api/tracking/upload as we are using /api/update-tracking now
BATCH_TRACKING_STORE = {}

@app.post("/api/tracking/batch/{batch_id}")
async def process_tracking_batch(
    batch_id: str, 
    limit: int = 20,
    user: User = Depends(get_current_user)
):
    try:
        batch = BATCH_TRACKING_STORE.get(batch_id)
        if not batch:
            return JSONResponse(status_code=404, content={"error": "Batch not found"})
            
        items = batch["items"]
        processed_count = batch["processed"]
        total = batch["total"]
        
        if processed_count >= total:
            return {
                "sent": 0,
                "failed": 0,
                "remaining": 0,
                "items": []
            }
            
        # Get chunk
        chunk = items[processed_count : processed_count + limit]
        
        # Re-instantiate client (stateless preferred)
        token_data = TiendaNubeAuth.get_valid_token(batch["store_id"])
        if not token_data:
             return JSONResponse(status_code=401, content={"error": "Session expired during batch."})
             
        client = TiendaNubeClient(store_id=token_data["user_id"], access_token=token_data["access_token"])
        
        chunk_results = []
        sent_in_batch = 0
        failed_in_batch = 0
        
        for item in chunk:
            res = client.process_single_tracking_item(item)
            # Normalize result for response
            is_ok = (res.get("status") == "SUCCESS")
            
            if is_ok:
                sent_in_batch += 1
            else:
                failed_in_batch += 1
                
            chunk_results.append({
                "order_id": res.get("order"),
                "ok": is_ok,
                "error": res.get("details") if not is_ok else None,
                # Legacy fields for frontend compatibility if needed
                "status": res.get("status"), 
                "reason": res.get("details")
            })
            
        # Update State
        batch["results"].extend(chunk_results)
        batch["processed"] += len(chunk)
        
        return {
            "sent": sent_in_batch,
            "failed": failed_in_batch,
            "remaining": total - batch["processed"],
            "items": chunk_results
        }
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": "Internal Processing Error", "detail": str(e)})

@app.get("/orders-ready", response_class=HTMLResponse)
async def view_orders_ready(
    request: Request, 
    store: Store = Depends(get_current_store),
    user: User = Depends(get_current_user)
):
    if not store:
        return RedirectResponse("/settings") # Force select store
    
    # Store ID is correct and owned by user
    return templates.TemplateResponse("orders_ready.html", {
        "request": request,
        "active_store_id": store.id
    })

@app.get("/api/orders/ready")
async def api_list_orders_ready(
    page: int = 1, 
    per_page: int = 50, 
    q: str = None, 
    stage: str = None, 
    debug: bool = False,
    store: Store = Depends(get_current_store),
    user: User = Depends(get_current_user)
):
    try:
        if not store:
             return JSONResponse(status_code=400, content={
                 "ok": False,
                 "error": "No active store selected"
             })
             
        token_data = TiendaNubeAuth.get_valid_token(store.id)
        if not token_data:
             return JSONResponse(status_code=401, content={
                 "ok": False,
                 "error": "Not authenticated with Tienda Nube"
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
async def api_orders_stats(
    store: Store = Depends(get_current_store),
    user: User = Depends(get_current_user)
):
    if not store:
        return {"ok": False, "stats": {"unpacked": 0, "packed": 0}}

    token_data = TiendaNubeAuth.get_valid_token(store.id)
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
async def generate_andreani_csv_route(
    data: dict, 
    store: Store = Depends(get_current_store),
    user: User = Depends(get_current_user)
):
    nums = data.get("order_numbers", [])
    if not nums:
        return JSONResponse(status_code=400, content={"error": "No orders selected"})
    
    if not store:
        return JSONResponse(status_code=400, content={"error": "No active store"})

    token_data = TiendaNubeAuth.get_valid_token(store.id)
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
async def process_batch_route(
    data: dict, 
    store: Store = Depends(get_current_store),
    user: User = Depends(get_current_user)
):
    nums = data.get("order_numbers", [])
    if not nums:
        return JSONResponse(status_code=400, content={"error": "No orders selected"})
    
    if not store:
        return JSONResponse(status_code=400, content={"error": "No active store"})

    token_data = TiendaNubeAuth.get_valid_token(store.id)
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
async def get_batch_data(
    batch_id: str,
    user: User = Depends(get_current_user)
):
    data = BATCH_STORE.get(batch_id)
    if not data:
        return JSONResponse(status_code=404, content={"error": "Batch not found or expired"})
    return data

@app.post("/admin/cleanup-phantom-store")
async def cleanup_phantom_store(request: Request, session: Session = Depends(get_session)):
    admin_key = request.headers.get("X-ADMIN-KEY")
    expected_key = os.getenv("ADMIN_KEY")
    
    # If env var not set, for safety deny access or allow if explicit emptiness intended? 
    # Usually deny.
    if not expected_key or admin_key != expected_key:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    # 1. Find Store with tiendanube_user_id == 1
    query = select(Store).where(Store.tiendanube_user_id == 1)
    phantom_store = session.exec(query).first()
    
    if not phantom_store:
        return {"ok": True, "deleted": False, "message": "Phantom store (ID 1) not found."}

    try:
        # 2. Delete linked token first
        # Token relates to Store via store_id (SQLModel cascade might handle it, but manual is safer per request)
        query_token = select(TiendaNubeToken).where(TiendaNubeToken.store_id == phantom_store.id)
        token = session.exec(query_token).first()
        if token:
            session.delete(token)
        
        # 3. Delete Store
        name = phantom_store.name
        session.delete(phantom_store)
        session.commit()
        
        return {"ok": True, "deleted": True, "message": f"Deleted store '{name}' (ID {phantom_store.id}) and its token."}
    except Exception as e:
        session.rollback()
        return JSONResponse(status_code=500, content={"error": str(e)})
