import csv
import io
from datetime import datetime
import pandas as pd

class TiendaNubeCSVGenerator:
    COLUMNS = [
        "Número de orden", "Email", "Fecha", "Estado de la orden", "Estado del pago", 
        "Estado del envío", "Moneda", "Subtotal de productos", "Descuento", "Costo de envío", 
        "Total", "Nombre del comprador", "DNI / CUIT", "Teléfono", "Nombre para el envío", 
        "Teléfono para el envío", "Dirección", "Número", "Piso", "Localidad", 
        "Ciudad", "Código postal", "Provincia o estado", "País", "Forma de pago", 
        "Medio de envío", "Días mínimos de envío", "Días máximos de envío", "Cupón", 
        "Nota", "Tags", "Fecha de pago", "Fecha de envío", "Nombre del producto", 
        "Precio del producto", "Cantidad del producto", "SKU", "Canal", 
        "Código de tracking del envío", "Identificador de la transacción en el medio de pago", 
        "Identificador de la orden", "Producto Físico", 
        "Persona que registró la venta", "Sucursal de venta", "Vendedor", 
        "Fecha y hora de cancelación", "Motivo de cancelación"
    ]

    @staticmethod
    def _fmt_date(iso_str, include_time=False):
        if not iso_str:
            return ""
        try:
            # TiendaNube ISO format usually: "2025-02-27T10:30:00+0000" or similar
            # If standard isoformat, use datetime.fromisoformat
            dt = datetime.fromisoformat(str(iso_str).replace('Z', '+00:00'))
            if include_time:
                return dt.strftime("%d/%m/%Y %H:%M")
            return dt.strftime("%d/%m/%Y")
        except:
            return str(iso_str)

    @staticmethod
    def _map_status(val, mapping):
        return mapping.get(val, val)

    @staticmethod
    def _clean(val):
        if val is None: 
            return ""
        s = str(val).strip()
        if s.lower() in ("none", "nan"):
            return ""
        return s

    @staticmethod
    def _fmt_num(val):
        if val is None: return ""
        try:
            f = float(val)
            # 2 decimals, point separator
            return f"{f:.2f}"
        except:
            return str(val)

    @classmethod
    def generate(cls, orders: list) -> str:
        rows = []
        
        status_map = {"open": "Abierta", "closed": "Cerrada", "cancelled": "Cancelada"}
        pay_map = {"paid": "Recibido", "pending": "Pendiente", "voided": "Cancelado"}
        ship_map = {"unshipped": "Listo para enviar", "shipped": "Enviado", "unpacked": "Listo para enviar"}
        
        for order in orders:
            # Common Order Fields
            shipping = order.get("shipping_address", {}) or {}
            
            common = {
                "Número de orden": cls._clean(order.get("number")),
                "Email": cls._clean(order.get("contact_email")),
                "Fecha": cls._fmt_date(order.get("created_at"), include_time=True),
                "Estado de la orden": cls._map_status(order.get("status"), status_map),
                "Estado del pago": cls._map_status(order.get("payment_status"), pay_map),
                "Estado del envío": cls._map_status(order.get("shipping_status"), ship_map),
                "Moneda": cls._clean(order.get("currency")),
                "Subtotal de productos": cls._fmt_num(order.get("subtotal")),
                "Descuento": cls._fmt_num(order.get("discount")),
                "Costo de envío": cls._fmt_num(order.get("shipping_cost_customer") or 0),
                "Total": cls._fmt_num(order.get("total")),
                "Nombre del comprador": cls._clean(order.get("contact_name") or order.get("billing_name")),
                "DNI / CUIT": cls._clean(order.get("contact_identification")),
                "Teléfono": cls._clean(order.get("contact_phone")),
                
                # Shipping
                "Nombre para el envío": cls._clean(shipping.get("name")),
                "Teléfono para el envío": cls._clean(shipping.get("phone")),
                "Dirección": cls._clean(shipping.get("address")),
                "Número": cls._clean(shipping.get("number")),
                "Piso": cls._clean(shipping.get("floor")),
                "Localidad": cls._clean(shipping.get("locality")),
                "Ciudad": cls._clean(shipping.get("city")),
                "Código postal": cls._clean(shipping.get("zipcode")),
                "Provincia o estado": cls._clean(shipping.get("province")),
                "País": cls._clean(shipping.get("country")),
                
                "Forma de pago": cls._clean(order.get("gateway_name")),
                "Medio de envío": cls._clean(order.get("shipping_option") or order.get("shipping_carrier_name")),
                "Días mínimos de envío": cls._clean(order.get("shipping_min_days")),
                "Días máximos de envío": cls._clean(order.get("shipping_max_days")),
                "Cupón": cls._clean(order.get("coupon")), # Assuming simplest structure
                "Nota": cls._clean(order.get("note")),
                "Tags": "", # Logic for tags if available
                "Fecha de pago": cls._fmt_date(order.get("paid_at")),
                "Fecha de envío": cls._fmt_date(order.get("shipped_at")),
                
                "Canal": "Móvil" if order.get("storefront") == "mobile" else "Escritorio",
                "Código de tracking del envío": "", # Override below
                "Identificador de la transacción en el medio de pago": cls._clean(order.get("gateway_id")),
                "Identificador de la orden": cls._clean(order.get("id")),
                "Producto Físico": "Sí" if order.get("has_shippable_products") else "No",
                
                # Empty fields
                "Persona que registró la venta": "",
                "Sucursal de venta": "",
                "Vendedor": "",
                "Fecha y hora de cancelación": "",
                "Motivo de cancelación": ""
            }
            
            # Tracking logic
            fulfillments = order.get("fulfillments", [])
            if fulfillments and isinstance(fulfillments, list):
                # Try to get first tracking code
                ft = fulfillments[0].get("tracking_info", {})
                if ft:
                    common["Código de tracking del envío"] = cls._clean(ft.get("code"))
            
            products = order.get("products", [])
            if not products:
                # Add 1 row with empty product info if needed, or skip? 
                # Usually valid orders have products. If no products, we output 1 row just in case.
                row = common.copy()
                rows.append(row)
            else:
                for p in products:
                    row = common.copy()
                    row["Nombre del producto"] = cls._clean(p.get("name"))
                    row["Precio del producto"] = cls._fmt_num(p.get("price"))
                    row["Cantidad del producto"] = cls._clean(p.get("quantity"))
                    row["SKU"] = cls._clean(p.get("sku"))
                    rows.append(row)
                    
        # Write to Buffer
        output = io.StringIO()
        # Ensure ONLY defined columns are written
        writer = csv.DictWriter(output, fieldnames=cls.COLUMNS, delimiter=";", lineterminator="\n", extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
        
        # Convert to bytes with Latin1
        try:
            content = output.getvalue().encode("latin-1", errors="replace")
        except Exception as e:
            # Fallback to mostly compatible
             content = output.getvalue().encode("iso-8859-1", errors="replace")
             
        return content
