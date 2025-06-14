from flask import Flask, render_template, request, redirect, flash, url_for, session
from dotenv import load_dotenv
import os
import requests
import json
from datetime import datetime, date
from requests.auth import HTTPBasicAuth

load_dotenv()
app = Flask(__name__)
app.secret_key = 'secret-key'

WC_STORE_URL = os.getenv("WC_STORE_URL")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")
LOG_FILE = "sales_log.json"

# Admin kullanıcı bilgileri (şifreyi .env dosyasından al)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "root")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "dzX81st!")

# Login kontrolü decorator - EN BAŞTA TANIMLA
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Satış loguna ekle
def log_sale(product_id, product_name, quantity, price, total_amount):
    log_entry = {
        "product_id": product_id,
        "product_name": product_name,
        "quantity": quantity,
        "price": price,
        "total_amount": total_amount,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    else:
        logs = []
    logs.append(log_entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

# Tüm ürünleri çek (pagination ile)
def get_all_products():
    all_products = []
    page = 1
    per_page = 100
    
    while True:
        url = f"{WC_STORE_URL}/wp-json/wc/v3/products?per_page={per_page}&page={page}"
        response = requests.get(url, auth=HTTPBasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET))
        
        if response.status_code == 200:
            products = response.json()
            if not products:  # Eğer boş liste gelirse dur
                break
            all_products.extend(products)
            page += 1
        else:
            break
    
    return all_products

# Tüm siparişleri çek (pagination ile)
def get_all_orders():
    all_orders = []
    page = 1
    per_page = 100
    
    while True:
        url = f"{WC_STORE_URL}/wp-json/wc/v3/orders?per_page={per_page}&page={page}"
        response = requests.get(url, auth=HTTPBasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET))
        
        if response.status_code == 200:
            orders = response.json()
            if not orders:  # Eğer boş liste gelirse dur
                break
            all_orders.extend(orders)
            page += 1
        else:
            break
    
    return all_orders

# Login sayfası
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            flash("✅ Başarılı giriş!")
            return redirect(url_for('list_products'))
        else:
            flash("❌ Kullanıcı adı veya şifre hatalı!")
    
    return render_template("login.html")

# Çıkış
@app.route("/logout")
def logout():
    session.clear()
    flash("👋 Çıkış yapıldı!")
    return redirect(url_for('login'))

# WooCommerce API'den ürünleri çek
@app.route("/products")
@login_required
def list_products():
    products = get_all_products()
    
    log_data = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            log_data = json.load(f)

    if products:
        total_stock = sum(int(p.get('stock_quantity', 0) or 0) for p in products)
        total_sales = sum(int(p.get('total_sales', 0) or 0) for p in products)
        total_revenue = sum(float(p.get('price', 0) or 0) * int(p.get('total_sales', 0) or 0) for p in products)
        sold_count = sum(1 for p in products if int(p.get('stock_quantity') or 0) == 0)
        in_stock_count = sum(1 for p in products if int(p.get('stock_quantity') or 0) > 0)

        # Günlük satışları hesapla
        today_str = date.today().strftime("%Y-%m-%d")
        daily_sales = [l for l in log_data if l['timestamp'].startswith(today_str)]
        daily_sales_count = len(daily_sales)
        daily_sales_names = [l['product_name'] for l in daily_sales]
        
        # Günlük gelir hesapla
        daily_revenue = sum(float(l.get('total_amount', 0)) for l in daily_sales)

        return render_template("products.html",
            products=products,
            total_stock=total_stock,
            total_sales=total_sales,
            total_revenue=total_revenue,
            sold_count=sold_count,
            in_stock_count=in_stock_count,
            sales_log=log_data,
            daily_sales_count=daily_sales_count,
            daily_sales_names=daily_sales_names,
            daily_revenue=daily_revenue
        )
    else:
        flash("❌ Ürünler alınamadı!")
        return redirect("/")

# Siparişler sayfası
@app.route("/orders")
@login_required
def list_orders():
    orders = get_all_orders()
    
    if orders:
        # Siparişleri tarihe göre sırala (en yeni en üstte)
        orders.sort(key=lambda x: x.get('date_created', ''), reverse=True)
        
        # İstatistikleri hesapla
        total_orders = len(orders)
        pending_orders = len([o for o in orders if o.get('status') == 'pending'])
        processing_orders = len([o for o in orders if o.get('status') == 'processing'])
        completed_orders = len([o for o in orders if o.get('status') == 'completed'])
        cancelled_orders = len([o for o in orders if o.get('status') == 'cancelled'])
        
        # Toplam satış tutarı
        total_sales_amount = sum(float(o.get('total', 0)) for o in orders if o.get('status') in ['completed', 'processing'])
        
        # Bugünün siparişleri
        today_str = date.today().strftime("%Y-%m-%d")
        today_orders = [o for o in orders if o.get('date_created', '').startswith(today_str)]
        today_orders_count = len(today_orders)
        today_sales_amount = sum(float(o.get('total', 0)) for o in today_orders)

        return render_template("orders.html",
            orders=orders[:50],  # İlk 50 siparişi göster
            total_orders=total_orders,
            pending_orders=pending_orders,
            processing_orders=processing_orders,
            completed_orders=completed_orders,
            cancelled_orders=cancelled_orders,
            total_sales_amount=total_sales_amount,
            today_orders_count=today_orders_count,
            today_sales_amount=today_sales_amount
        )
    else:
        flash("❌ Siparişler alınamadı!")
        return redirect(url_for('list_products'))

# Ürünü satıldı olarak işaretle (quantity ile)
@app.route("/mark_sold/<int:product_id>")
@login_required
def mark_sold(product_id):
    quantity = int(request.args.get('quantity', 1))  # Frontend'den gelen miktar
    
    # Önce ürün bilgilerini al
    get_url = f"{WC_STORE_URL}/wp-json/wc/v3/products/{product_id}"
    product_response = requests.get(get_url, auth=HTTPBasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET))
    
    if product_response.status_code == 200:
        product = product_response.json()
        current_stock = int(product.get('stock_quantity', 0) or 0)
        
        # Eğer satılacak miktar stoktan fazlaysa uyarı ver
        if quantity > current_stock:
            flash(f"❌ Hata: Stokta sadece {current_stock} adet var!")
            return redirect(url_for('list_products'))
        
        # Mevcut stoktan satılan miktarı çıkar
        new_stock = current_stock - quantity
        
        # Fiyat bilgisini al
        price = float(product.get('price', 0) or 0)
        total_amount = price * quantity
        
        # Satış loguna ekle
        log_sale(product_id, f"{product.get('name', 'Bilinmeyen Ürün')}", quantity, price, total_amount)

        # Stoğu güncelle
        url = f"{WC_STORE_URL}/wp-json/wc/v3/products/{product_id}"
        data = {"stock_quantity": new_stock, "manage_stock": True}
        response = requests.put(url, auth=HTTPBasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET), json=data)

        if response.status_code == 200:
            flash(f"✅ {quantity} adet satıldı. Kalan stok: {new_stock}")
        else:
            flash("❌ Hata: " + response.text)
    else:
        flash("❌ Ürün bulunamadı!")
        
    return redirect(url_for('list_products'))

# Ürün stoğunu güncelle
@app.route("/update_stock", methods=["POST"])
@login_required
def update_stock():
    product_id = request.form.get("product_id")
    stock_quantity = request.form.get("stock_quantity")

    url = f"{WC_STORE_URL}/wp-json/wc/v3/products/{product_id}"
    data = {"stock_quantity": int(stock_quantity), "manage_stock": True}

    response = requests.put(url, auth=HTTPBasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET), json=data)

    if response.status_code == 200:
        flash("✅ Stok güncellendi.")
    else:
        flash("❌ Hata: " + response.text)
    return redirect(url_for('list_products'))

# Sipariş durumunu güncelle
@app.route("/update_order_status", methods=["POST"])
@login_required
def update_order_status():
    order_id = request.form.get("order_id")
    new_status = request.form.get("status")

    url = f"{WC_STORE_URL}/wp-json/wc/v3/orders/{order_id}"
    data = {"status": new_status}

    response = requests.put(url, auth=HTTPBasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET), json=data)

    if response.status_code == 200:
        flash(f"✅ Sipariş #{order_id} durumu '{new_status}' olarak güncellendi.")
    else:
        flash("❌ Hata: " + response.text)
    return redirect(url_for('list_orders'))

@app.route("/")
def index():
    if 'logged_in' in session:
        return redirect(url_for('list_products'))
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=8082)