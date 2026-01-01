import os
import json
import requests
import pandas as pd
import io
import re
import PyPDF2
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
from sqlmodel import select
from app.models import TiendaNubeToken, Store, User

# ... imports ...

    @staticmethod
    def exchange_code_for_token(code):
        # ... (validation code remains the same) ...

        # If we reached here, data is valid
        print(f"Token Exchange Success. User ID (TN Store ID): {user_id}")

        store_id_internal = None

        # Save to DB
        with next(get_session()) as session:
            # 0. Ensure Admin User Exists (Sprint 2 Temporary)
            admin_user_id = 1
            admin_user = session.get(User, admin_user_id)
            if not admin_user:
                print("Admin User (ID 1) not found. Creating default admin.")
                admin_user = User(
                    id=1, # Force ID 1
                    email="admin@example.com",
                    password_hash="pbkdf2:sha256:260000$placeholder$hash", # Placeholder, auth not active yet
                    is_admin=True
                )
                session.add(admin_user)
                session.commit()
                # No refresh needed, we know ID is 1
            
            # 1. Find or Create Store
            statement_store = select(Store).where(Store.tiendanube_user_id == int(user_id))
            store = session.exec(statement_store).first()
            
            if not store:
                print(f"New Store detected for TN ID {user_id}. Creating...")
                
                store = Store(
                    name=f"Tienda {user_id}",
                    tiendanube_user_id=int(user_id),
                    user_id=admin_user_id
                )
                session.add(store)
                session.commit()
                session.refresh(store)
            
            store_id_internal = store.id
            
            # 2. Update/Create Token linked to this Store
            # ... (rest remains same) ...
            # Check existence by Store ID (preferred) or User ID
            statement_token = select(TiendaNubeToken).where(TiendaNubeToken.store_id == store.id)
            existing_token = session.exec(statement_token).first()
            
            encrypted_access_token = encrypt_token(access_token)
            
            if existing_token:
                existing_token.access_token_encrypted = encrypted_access_token
                existing_token.token_type = token_type
                existing_token.scope = token_data.get("scope")
                existing_token.user_id = int(user_id) # Ensure consistency
                session.add(existing_token)
            else:
                new_token = TiendaNubeToken(
                    access_token_encrypted=encrypted_access_token,
                    token_type=token_type,
                    scope=token_data.get("scope"),
                    user_id=int(user_id),
                    store_id=store.id
                )
                session.add(new_token)
            
            session.commit()
            
        # Return merged data including our internal store_id
        token_data["store_id"] = store_id_internal
        return token_data

    @staticmethod
    def get_valid_token(store_id: int = None):
        # Retrieve latest token for specific store
        if not store_id:
             # Fallback? Or fail? User requested explicit selector.
             # Ideally we shouldn't guess, but for backwards compatibility...
             return None 

        with next(get_session()) as session:
            # Join with Store to be safe? Or just filter by store_id if Token has it.
            # Token model has store_id.
            statement = select(TiendaNubeToken).where(TiendaNubeToken.store_id == store_id)
            results = session.exec(statement)
            token_db = results.first()
            
            if not token_db:
                return None
            
            # Decrypt validation
            try:
                decrypted = decrypt_token(token_db.access_token_encrypted)
            except Exception as e:
                print(f"Decryption Error: {e}") 
                return None
                
            return {
                "access_token": decrypted,
                "user_id": token_db.user_id,
                "token_type": token_db.token_type,
                "scope": token_db.scope,
                "store_id": token_db.store_id
            }

class TiendaNubeClient:
    def __init__(self, store_id: str, access_token: str):
        if not access_token:
            raise ValueError("Missing access_token (None/empty). Reconnect and regenerate tokens.json.")
        
        self.store_id = str(store_id)
        self.access_token = str(access_token).strip()
        self.base = f"https://api.tiendanube.com/v1/{self.store_id}"
        self.headers = {
            "Authentication": f"bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Antigravity-App/1.0"
        }

    def _req(self, method: str, url: str, **kwargs):
        r = requests.request(method, url, headers=self.headers, timeout=30, **kwargs)
        return r

    def lookup_real_order_id(self, order_number: int) -> int:
        url = f"{self.base}/orders"
        r = self._req("GET", url, params={"q": str(order_number)})
        if r.status_code != 200:
            raise RuntimeError(f"LOOKUP FAILED {r.status_code}: {r.text}")

        data = r.json()
        if not isinstance(data, list) or not data:
            raise RuntimeError(f"ORDER NOT FOUND for number={order_number}. Body={r.text}")

        # debería venir 1 sola
        real_id = data[0].get("id")
        if not real_id:
            raise RuntimeError(f"LOOKUP OK but missing id. Body={r.text}")

        return int(real_id)

    def get_order(self, real_order_id: int) -> dict:
        url = f"{self.base}/orders/{real_order_id}"
        # Solicitamos aggregates para intentar obtener objetos completos en 'fulfillments'
        # aunque igual soportaremos si devuelve solo IDs (strings)
        r = self._req("GET", url, params={"aggregates": "fulfillment_orders"})
        if r.status_code != 200:
            raise RuntimeError(f"GET ORDER FAILED {r.status_code}: {r.text}")
        return r.json()

    def patch_fulfillment_tracking(self, real_order_id: int, fulfillment_id: str, tracking_code: str, tracking_url: str | None):
        # Endpoint correcto según docs
        endpoint = f"{self.base}/orders/{real_order_id}/fulfillment-orders/{fulfillment_id}"

        payload = {
            "tracking_info": {
                "code": tracking_code,
                "url": tracking_url,
                "notify_customer": True
            }
            # Si querés forzar estado, se puede probar agregando:
            # ,"status": "DISPATCHED"
        }
        
        # User requested status DISPATCHED in previous turn, let's include it if payload supports it
        # Step 183: "status": "DISPATCHED"
        payload["status"] = "DISPATCHED"

        r = self._req("PATCH", endpoint, json=payload)
        return endpoint, r.status_code, r.text

    def list_orders_ready(self, page: int = 1, per_page: int = 20, q: str = None, payment_statuses: list = None, stage: str = None, debug: bool = False) -> dict:
        url = f"{self.base}/orders"
        params = {
            "page": page,
            "per_page": per_page,
            "status": "open"
        }
        if q:
            params["q"] = str(q)

        if debug:
            print(f"DEBUG: Requesting orders {url} with params {params}") 
            
        r = self._req("GET", url, params=params)
        
        if r.status_code != 200:
            raise RuntimeError(f"LIST ORDERS FAILED {r.status_code}: {r.text}")
        
        data = r.json()
        if not isinstance(data, list):
            print(f"DEBUG: Unexpected response (not list): {data}")
            return {"results": [], "debug": []}

        if payment_statuses is None:
            payment_statuses = ["paid"]

        results = []
        debug_log = []

        for order in data:
            excluded_reason = None
            included = False
            
            # Extract basic info for debug
            oid = order.get("id")
            onum = order.get("number")
            ostatus = order.get("status")
            opay = order.get("payment_status")
            oship = order.get("shipping_status")
            onext = order.get("next_action")
            ofulls = order.get("fulfillments") or []
            
            f_status = None
            if ofulls:
                f_status = ofulls[0].get("status")

            # Evaluation Logic
            try:
                # 1. Status 'open'
                if ostatus != "open": 
                    excluded_reason = f"status '{ostatus}' != 'open'"
                
                # 2. Payment Status Check
                elif opay not in payment_statuses:
                    excluded_reason = f"payment_status != 'paid' ({opay})"
                
                # 3. Fulfillment Stage Logic
                elif stage:
                    if stage == 'unpacked':
                        # Criteria for 'Por Empaquetar':
                        # - fulfillments exists AND status is 'unpacked'
                        # - OR fulfillments empty (waiting to be created)
                        # - OR next_action is 'waiting_packing'
                        is_unpacked_candidate = False
                        
                        if ofulls:
                            if str(f_status).lower() == 'unpacked':
                                is_unpacked_candidate = True
                            else:
                                excluded_reason = f"stage='unpacked' but fulfillments[0].status='{f_status}'"
                        elif onext == 'waiting_packing':
                            is_unpacked_candidate = True
                            f_status = "unpacked (next_action)"
                        else:
                            # Fallback: validation for empty fulfillments without explicit next_action?
                            # Previous logic allowed empty fulfillments.
                            # We keep it permissive for 'unpacked' if no contradictory info exists.
                            is_unpacked_candidate = True 
                            f_status = "pending_creation"
                        
                        if not is_unpacked_candidate and not excluded_reason:
                            excluded_reason = "stage='unpacked' criteria not met"
                    
                    elif stage == 'packed':
                        # Criteria for 'Por Enviar':
                        # - Must have fulfillments
                        # - Status must be 'packed'
                        if not ofulls:
                            excluded_reason = "stage='packed' but no fulfillments"
                        elif str(f_status).lower() != 'packed':
                             excluded_reason = f"stage='packed' but fulfillments[0].status='{f_status}'"
                
                # 4. Shipping 'unshipped' or 'unpacked'
                if not excluded_reason:
                     # FIX: Accept "unpacked" as valid for ready orders (User Request)
                     if oship not in ["unshipped", "unpacked"]:
                         excluded_reason = f"shipping_status '{oship}' not in ['unshipped', 'unpacked']"

                # Final Decision
                if not excluded_reason:
                    included = True

            except Exception as e:
                excluded_reason = f"EXCEPTION: {str(e)}"
            
            # DEBUG ENTRY construction
            if debug:
                debug_entry = {
                    "number": onum,
                    "id": oid,
                    "status": ostatus,
                    "payment_status": opay,
                    "shipping_status": oship,
                    "next_action": onext,
                    "fulfillments_count": len(ofulls),
                    "fulfillment_status_0": f_status,
                    "stage_requested": stage,
                    "included": included,
                    "excluded_reason": excluded_reason
                }
                debug_log.append(debug_entry)
            
            if included:
                try:
                     # Extract logic for result
                    shipping_address = order.get("shipping_address") or {}
                    if not isinstance(shipping_address, dict): shipping_address = {}
                    
                    c_name = order.get("contact_name")
                    if not c_name: c_name = order.get("contact_email")
                    
                    products_raw = order.get("products", [])
                    products_list = []
                    for p in products_raw:
                        products_list.append({
                            "name": p.get("name"),
                            "sku": p.get("sku"),
                            "quantity": p.get("quantity"),
                            "variant": p.get("variant_name")
                        })
                        
                    results.append({
                        "number": onum,
                        "id": oid,
                        "created_at": order.get("created_at"),
                        "customer_name": c_name,
                        "zipcode": shipping_address.get("zipcode"),
                        "province": shipping_address.get("province"),
                        "city": shipping_address.get("city"),
                        "shipping_option": order.get("shipping_option"),
                        "payment_status": opay,
                        "shipping_status": oship,
                        "fulfillment_status": f_status,
                        "address": shipping_address.get("address"),
                        "products": products_list
                    })
                except Exception as e:
                    print(f"ERROR building result for {onum}: {e}")
                    if debug: debug_log[-1]["excluded_reason"] = f"BUILD ERROR: {e}"
                    
        return {"results": results, "debug": debug_log}

    def get_order_stats(self) -> dict:
        """
        Calculates counts for 'unpacked' and 'packed' based on recent open orders.
        Applies STRICT filtering matching list_orders_ready.
        """
        url = f"{self.base}/orders"
        # Fetch a reasonable batch to get stats
        params = {"page": 1, "per_page": 100, "status": "open"}
        
        try:
            r = self._req("GET", url, params=params)
            if r.status_code != 200: return {"unpacked": 0, "packed": 0}
            data = r.json()
            if not isinstance(data, list): return {"unpacked": 0, "packed": 0}
        except:
            return {"unpacked": 0, "packed": 0}

        unpacked_count = 0
        packed_count = 0
        
        for order in data:
            # 1. Status 'open'
            if order.get("status") != "open": continue
            
            # 2. Payment Status Check (STRICT PAID)
            if order.get("payment_status") != "paid": continue
            
            # 3. Shipping Status Check
            oship = order.get("shipping_status")
            if oship not in ["unshipped", "unpacked"]: continue
            
            # Fulfillment Info
            fulfillments = order.get("fulfillments") or []
            f_status = fulfillments[0].get("status") if fulfillments else None
            onext = order.get("next_action")

            # Check UNPACKED Criteria
            is_unpacked = False
            if fulfillments:
                if str(f_status).lower() == 'unpacked': is_unpacked = True
            elif onext == 'waiting_packing':
                is_unpacked = True
            else:
                # Fallback for empty fulfillments (pending creation)
                is_unpacked = True
            
            if is_unpacked:
                unpacked_count += 1
            
            # Check PACKED Criteria (Independent check, though usually mutually exclusive)
            is_packed = False
            if fulfillments and str(f_status).lower() == 'packed':
                is_packed = True
            
            if is_packed:
                packed_count += 1

        return {"unpacked": unpacked_count, "packed": packed_count}

    def send_tracking_for_order_number(self, order_number: int, tracking_code: str, tracking_url: str | None = None) -> dict:
        # 1) buscar ID real
        real_id = self.lookup_real_order_id(order_number)

        # 2) traer orden (acá viene 'fulfillments')
        order = self.get_order(real_id)

        fulfillments = order.get("fulfillments", [])
        if not isinstance(fulfillments, list) or len(fulfillments) == 0:
            # Check fallback to fulfillment_orders just in case
            fulfillments = order.get("fulfillment_orders", [])
            if not isinstance(fulfillments, list) or len(fulfillments) == 0:
                 raise RuntimeError(f"Order {order_number} (real {real_id}) has no fulfillments. Keys={list(order.keys())}")

        # 3) tomar el primero (si manejás multi-bulto, acá tendrías que matchear cuál)
        f0 = fulfillments[0]
        
        # Robust handling: f0 can be a dict (object) or str (id)
        if isinstance(f0, dict):
            fulfillment_id = f0.get("id")
            if not fulfillment_id:
                raise RuntimeError(f"Missing fulfillment id in fulfillments[0] dict. value={f0}")
        elif isinstance(f0, str):
            fulfillment_id = f0
        else:
             raise RuntimeError(f"Unexpected fulfillments[0] type: {type(f0)} value={f0}")

        # 4) patch tracking
        endpoint, status, body = self.patch_fulfillment_tracking(real_id, fulfillment_id, tracking_code, tracking_url)

        return {
            "order_number": order_number,
            "real_order_id": real_id,
            "fulfillment_id": fulfillment_id,
            "endpoint": endpoint,
            "http_status": status,
            "body": body
        }
        
    def _extract_from_pdf(self, file_content):
        """
        Extracts (order_id, tracking_number) tuples from an Andreani PDF.
        """
        results = []
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            for page in reader.pages:
                text = page.extract_text()
                if not text:
                    continue
                
                # Normalize text for regex
                clean_text = text.replace("N°", "").replace("Nº", "").replace("\n", " ")
                
                # 1. Find Order ID
                order_match = re.search(r"Interno\s*:\s*#?\s*([0-9]+)", clean_text, re.IGNORECASE)
                order_id = None
                if order_match:
                    order_id = order_match.group(1)
                
                # 2. Find Tracking Number
                tracking_number = None
                tracking_match = re.search(r"de seguimiento\s*:\s*([0-9]+)", clean_text, re.IGNORECASE)
                if tracking_match:
                    tracking_number = tracking_match.group(1)
                else:
                    fallback_match = re.search(r"(?:Envío|Seguimiento)\s*(?:Andreani)?\s*:?\s*([A-Z0-9]+)", clean_text, re.IGNORECASE)
                    if fallback_match:
                        tracking_number = fallback_match.group(1)
                
                if order_id and tracking_number:
                    results.append({"order": order_id, "track": tracking_number})
                    
        except Exception as e:
            print(f"Error parsing PDF: {e}")
            raise e
            
        return pd.DataFrame(results)

    def process_tracking_file(self, file_content):
        # Determine file type
        try:
            if file_content.startswith(b"%PDF"):
                 df = self._extract_from_pdf(file_content)
                 if df.empty:
                     return {"error": "No valid labels found in PDF. Could not identify 'Interno.'"}
            else:
                try:
                    df = pd.read_excel(io.BytesIO(file_content))
                except:
                    df = pd.read_csv(io.BytesIO(file_content), sep=None, engine='python')
        except Exception as e:
             return {"error": f"Could not read file: {str(e)}"}

        if not 'order' in df.columns:
            df.columns = [str(c).lower().strip() for c in df.columns]
            col_order = next((c for c in df.columns if "orden" in c or "numero" in c or "id" in c), None)
            col_track = next((c for c in df.columns if "seguimiento" in c or "track" in c or "codigo" in c), None)
            
            if not col_order or not col_track:
                return {"error": "Could not identify columns."}
            df.rename(columns={col_order: "order", col_track: "track"}, inplace=True)

        results = []
        for _, row in df.iterrows():
            order_number = str(row["order"]).strip()
            if order_number.endswith(".0"): order_number = order_number[:-2]
            track_code = str(row["track"]).strip()
            
            if not order_number or not track_code or track_code.lower() == "nan":
                results.append({"order": order_number, "status": "SKIPPED", "reason": "Empty data"})
                continue

            try:
                # Use the helper method for logic
                track_url = f"https://seguimiento.andreani.com/envio/{track_code}"
                result_data = self.send_tracking_for_order_number(order_number, track_code, track_url)
                
                # Check status
                status_code = result_data.get("http_status")
                if status_code in [200, 201]:
                     results.append({
                        "order": order_number, 
                        "status": "SUCCESS", 
                        "details": f"Updated. Real ID: {result_data.get('real_order_id')}"
                     })
                else:
                    details = f"Endpoint: {result_data.get('endpoint')} | Status: {status_code} | Body: {result_data.get('body')}"
                    results.append({"order": order_number, "status": "ERROR", "details": details})
                    
            except Exception as e:
                results.append({"order": order_number, "status": "EXCEPTION", "details": str(e)})
                
        return {"results": results}
