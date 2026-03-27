from dotenv import load_dotenv
import os

load_dotenv()

import razorpay
import pandas as pd
from flask import (
    Flask, jsonify, render_template, request,
    redirect, session, flash, url_for, send_file
)

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

from werkzeug.security import generate_password_hash, check_password_hash

from flask_mail import Mail, Message
from flask_wtf.csrf import CSRFProtect

from functools import wraps

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

from datetime import datetime
import random
import string

# -------------------------------------------------
# CREATE FLASK APP
# -------------------------------------------------

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

# -------------------------------------------------
# ENABLE CSRF PROTECTION
# -------------------------------------------------

csrf = CSRFProtect(app)

# -------------------------------------------------
# DATABASE CONFIG
# -------------------------------------------------

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# -------------------------------------------------
# MAIL CONFIG
# -------------------------------------------------

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

mail = Mail(app)

# -------------------------------------------------
# RAZORPAY CONFIG
# -------------------------------------------------

razorpay_client = razorpay.Client(
    auth=(
        os.getenv("RAZORPAY_KEY"),
        os.getenv("RAZORPAY_SECRET")
    )
)

# -------------------------------------------------
# ADMIN CONFIG
# -------------------------------------------------

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper
def get_categories():
    return [
        "Men",
        "Women",
        "Footwear",
        "Accessories"
    ]
# -------------------------------------------------
# MODELS
# -------------------------------------------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True, index=True)
    password = db.Column(db.String(255))

class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))
    description = db.Column(db.Text)
    brand = db.Column(db.String(100))
    tags = db.Column(db.Text)
    image_url = db.Column(db.Text)
    rating = db.Column(db.Float, default=0)
    review_count = db.Column(db.Integer, default=0)
    price = db.Column(db.Float, nullable=False, default=0)

class Cart(db.Model):
    __tablename__ = "cart"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(
    db.Integer,
    db.ForeignKey("products.id", ondelete="CASCADE"),
    nullable=False
)


    quantity = db.Column(db.Integer, default=1)
class Wishlist(db.Model):
    __tablename__ = "wishlist"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)

class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50))
    payment_method = db.Column(db.String(50), default="UPI")
    status = db.Column(db.String(20), default="Pending")
    tracking_id = db.Column(db.String(100), unique=True)
    user_id = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)

    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(50), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)

class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
class Review(db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)

    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)
            
            
            #helper function recomandation 


class RecentlyViewed(db.Model):
    __tablename__ = "recently_viewed"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=False
    )

    viewed_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

def get_recently_viewed_products(user_id, limit=6):

    views = (
        RecentlyViewed.query
        .filter_by(user_id=user_id)
        .order_by(RecentlyViewed.viewed_at.desc())
        .limit(limit)
        .all()
    )

    product_ids = [v.product_id for v in views]

    if not product_ids:
        return []

    products = Product.query.filter(
        Product.id.in_(product_ids)
    ).all()

    return products
def customers_also_bought(product_id, limit=6):

    order_items = OrderItem.query.filter_by(
        product_id=product_id
    ).all()

    order_ids = [item.order_id for item in order_items]

    if not order_ids:
        return []

    related_items = OrderItem.query.filter(
        OrderItem.order_id.in_(order_ids),
        OrderItem.product_id != product_id
    ).all()

    related_product_ids = list(
        set([item.product_id for item in related_items])
    )

    return Product.query.filter(
        Product.id.in_(related_product_ids)
    ).limit(limit).all()

def rank_products_for_user(products, user_id):

    scores = {}

    for product in products:
        scores[product.id] = 0

    # ---------------- PURCHASE SCORE ----------------
    orders = db.session.query(OrderItem.product_id)\
        .join(Order)\
        .filter(Order.user_id == user_id)\
        .all()

    for o in orders:
        if o.product_id in scores:
            scores[o.product_id] += 5

    # ---------------- WISHLIST ----------------
    wishlist = Wishlist.query.filter_by(
        user_id=user_id
    ).all()

    for w in wishlist:
        if w.product_id in scores:
            scores[w.product_id] += 4

    # ---------------- CART ----------------
    cart = Cart.query.filter_by(
        user_id=user_id
    ).all()

    for c in cart:
        if c.product_id in scores:
            scores[c.product_id] += 3

    # ---------------- RECENTLY VIEWED ----------------
    views = RecentlyViewed.query.filter_by(
        user_id=user_id
    ).all()

    for v in views:
        if v.product_id in scores:
            scores[v.product_id] += 2

    # ---------------- SORT PRODUCTS ----------------
    ranked_products = sorted(
        products,
        key=lambda p: scores[p.id],
        reverse=True
    )
    

    return ranked_products
def get_trending_products(limit=8):

    trending = db.session.query(
        OrderItem.product_id,
        db.func.count(OrderItem.product_id).label("total")
    ).group_by(
        OrderItem.product_id
    ).order_by(
        db.desc("total")
    ).limit(limit).all()

    product_ids = [t.product_id for t in trending]

    if not product_ids:
        return Product.query.limit(limit).all()

    return Product.query.filter(
        Product.id.in_(product_ids)
    ).all()
def recommend_for_user(user_id, limit=8):

    product_ids = set()

    # ---------------- ORDERS ----------------
    orders = db.session.query(OrderItem.product_id)\
        .join(Order)\
        .filter(Order.user_id == user_id)\
        .all()

    for o in orders:
        product_ids.add(o.product_id)

    # ---------------- WISHLIST ----------------
    wishlist = Wishlist.query.filter_by(
        user_id=user_id
    ).all()

    for w in wishlist:
        product_ids.add(w.product_id)

    # ---------------- CART ----------------
    cart = Cart.query.filter_by(
        user_id=user_id
    ).all()

    for c in cart:
        product_ids.add(c.product_id)

    # ---------------- RECENTLY VIEWED ----------------
    views = RecentlyViewed.query.filter_by(
        user_id=user_id
    ).all()

    for v in views:
        product_ids.add(v.product_id)

    # Cold start fallback
    if not product_ids:
        return Product.query.limit(limit).all()

    base_products = Product.query.filter(
        Product.id.in_(product_ids)
    ).all()

    recommendations = []

    for product in base_products:
        recommendations.extend(
            get_similar_products(product, top_n=3)
        )

    # Remove duplicates
    unique_products = {
        p.id: p for p in recommendations
    }.values()

    return list(unique_products)[:limit]
def build_user_taste_profile(user_id):

    category_score = {}
    brand_score = {}

    interacted_products = set()

    # -------- ORDERS --------
    orders = db.session.query(OrderItem.product_id)\
        .join(Order)\
        .filter(Order.user_id == user_id)\
        .all()

    for o in orders:
        interacted_products.add(o.product_id)

    # -------- WISHLIST --------
    wishlist = Wishlist.query.filter_by(
        user_id=user_id
    ).all()

    for w in wishlist:
        interacted_products.add(w.product_id)

    # -------- CART --------
    cart = Cart.query.filter_by(
        user_id=user_id
    ).all()

    for c in cart:
        interacted_products.add(c.product_id)

    # -------- RECENTLY VIEWED --------
    views = RecentlyViewed.query.filter_by(
        user_id=user_id
    ).all()

    for v in views:
        interacted_products.add(v.product_id)

    if not interacted_products:
        return {}, {}

    products = Product.query.filter(
        Product.id.in_(interacted_products)
    ).all()

    # -------- BUILD SCORES --------
    for p in products:

        if p.category:
            category_score[p.category] = \
                category_score.get(p.category, 0) + 1

        if p.brand:
            brand_score[p.brand] = \
                brand_score.get(p.brand, 0) + 1

    return category_score, brand_score
def recommend_by_taste(user_id, limit=8):

    category_score, brand_score = \
        build_user_taste_profile(user_id)

    if not category_score:
        return Product.query.limit(limit).all()

    top_category = max(
        category_score,
        key=category_score.get
    )

    products = Product.query.filter_by(
        category=top_category
    ).limit(limit).all()

    return products
def get_email_recommendations(user_id, limit=5):

    recommended = recommend_for_user(user_id)

    if not recommended:
        recommended = get_trending_products(limit)

    return recommended[:limit]

@app.route("/my-account")
@login_required
def my_account():

    user_id = session.get("user_id")

    # Get user
    user = db.session.get(User, user_id)

    if not user:
        flash("User not found", "danger")
        return redirect("/login")

    # Total orders
    total_orders = Order.query.filter_by(
        user_id=user_id
    ).count()

    # Total spent
    total_spent = db.session.query(
        func.sum(Order.total_amount)
    ).filter(
        Order.user_id == user_id
    ).scalar()

    total_spent = total_spent or 0

    return render_template(
        "my_account.html",
        user=user,
        total_orders=total_orders,
        total_spent=total_spent
    )
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Admin login required", "danger")
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper
# -------------------------------------------------
# HOME
# -------------------------------------------------
@app.route("/")
def home():

    products = Product.query.all()
    categories = get_categories()
    recently_viewed = []
    recommended_products = []
    trending_products = get_trending_products()
    taste_products = []


    if "user_id" in session:
        user_id = session["user_id"]
        
        recently_viewed = get_recently_viewed_products(
            session["user_id"]
        )
        
        recommended_products = recommend_for_user(
            user_id
        )

        recommended_products = rank_products_for_user(
            recommended_products,
            user_id
        )
        taste_products = recommend_by_taste(user_id)

    

    return render_template(
        "home.html",
        products=products,
        recently_viewed=recently_viewed,
        categories=categories,
        recommended_products=recommended_products,
        trending_products=trending_products,
        taste_products=taste_products
    )

# -------------------------------------------------
# AUTH
# -------------------------------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("Email already registered", "warning")
            return redirect("/signup")

        # Hash password
        hashed_password = generate_password_hash(password)

        user = User(
            name=name,
            email=email,
            password=hashed_password
        )

        db.session.add(user)
        db.session.commit()

        flash("Signup successful. Please login.", "success")

        return redirect(url_for("login"))

    return render_template(
        "signup.html",
        categories=get_categories()
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        user = User.query.filter_by(
            email=request.form["email"]
        ).first()

        if user and check_password_hash(
            user.password,
            request.form["password"]
        ):
            session["user_id"] = user.id
            session["user_name"] = user.name
            return redirect("/products")

        flash("Invalid login credentials")

    return render_template(
        "login.html",
        categories=get_categories()
    )
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


#admin rotes 
# -------------------------------------------------
# ADMIN AUTH
# -------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:

            session.clear()
            session["admin_logged_in"] = True
            session["admin_user"] = username

            flash("Admin login successful", "success")

            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin credentials", "danger")

    return render_template("admin/login.html")
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template(
        "admin/dashboard.html",
        total_products=Product.query.count(),
        total_orders=Order.query.count(),
        total_users=User.query.count()
    )

@app.route("/admin/products")
@admin_required
def admin_products():
    products = Product.query.order_by(Product.id.asc()).all()

    return render_template(
        "admin/products.html",
        products=products
    )
@app.route("/admin/products/add", methods=["GET", "POST"])
@admin_required
def admin_add_product():
    if request.method == "POST":
        product = Product(
            name=request.form["name"],
            price=float(request.form["price"]),
            category=request.form.get("category"),
            description=request.form.get("description"),
            brand=request.form.get("brand"),
            tags=request.form.get("tags"),
            image_url=request.form.get("image_url")
        )

        db.session.add(product)
        db.session.commit()
        flash("Product added successfully", "success")
        return redirect("/admin/products")

    return render_template(
        "admin/product_form.html",
        action="Add",
        product=None
    )
@app.route("/admin/products/edit/<int:id>", methods=["GET", "POST"])
@admin_required
def admin_edit_product(id):
    product = Product.query.get_or_404(id)

    if request.method == "POST":
        product.name = request.form["name"]
        product.price = float(request.form["price"])
        product.category = request.form.get("category")
        product.description = request.form.get("description")
        product.brand = request.form.get("brand")
        product.tags = request.form.get("tags")
        product.image_url = request.form.get("image_url")

        db.session.commit()
        flash("Product updated successfully", "success")
        return redirect("/admin/products")

    return render_template(
        "admin/product_form.html",
        action="Edit",
        product=product
    )


@app.route("/admin/products/delete/<int:id>")
@admin_required
def admin_delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted successfully", "warning")
    return redirect("/admin/products")
@app.route("/admin/orders")
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.id.desc()).all()
    return render_template(
        "admin/orders.html",
        orders=orders
    )

@app.route("/admin/orders/update/<int:order_id>", methods=["POST"])
@admin_required
def update_order_status(order_id):

    order = db.session.get(Order, order_id)
    new_status = request.form.get("status")
    new_tracking = request.form.get("tracking_id")

    # ✅ Update status
    order.status = new_status

    # 🔥 NEW ADDITION → Auto Tracking ID if empty
    if not new_tracking and new_status == "Shipped":
        import random
        import string

        while True:
            tracking_id = "PRS" + ''.join(random.choices(string.digits, k=8))
            exists = Order.query.filter_by(tracking_id=tracking_id).first()
            if not exists:
                break

        order.tracking_id = tracking_id
    else:
        order.tracking_id = new_tracking

    db.session.commit()

    # 🔥 EMAIL SEND WHEN STATUS CHANGES
    user = db.session.get(User, order.user_id)

    try:
        msg = Message(
            subject=f"Order {order.invoice_number} Status Updated",
            sender=app.config["MAIL_USERNAME"],
            recipients=[user.email]
        )

        msg.body = f"""
Hello {user.name},

Your order {order.invoice_number} status has been updated.

New Status: {order.status}

Tracking ID: {order.tracking_id or "Not Assigned"}

Thank you for shopping with us ❤️
"""

        mail.send(msg)

    except Exception as e:
        print("Status email failed:", e)

    flash("Order status updated + Email sent", "success")
    return redirect("/admin/orders")

# --------------------------------------------
# PRODUCTS
# --------------------------------------------
@app.route("/products")
def products():

    # Get selected category from URL
    selected_category = request.args.get("category")

    # Get selected brands from URL (multiple)
    selected_brands = request.args.getlist("brand")

    # Start base query
    query = Product.query

    # ✅ Apply category filter if selected
    if selected_category:
        query = query.filter(Product.category == selected_category)

    # ✅ Apply brand filter if selected
    if selected_brands:
        query = query.filter(Product.brand.in_(selected_brands))

    # Get final products
    products = query.all()

    return render_template(
        "products.html",
        products=products,
        categories=get_categories(),
        selected_brands=selected_brands,
        selected_category=selected_category  # Important for radio checked state
    )


@app.route("/product/<int:id>")
def product_details(id):
    product = Product.query.get_or_404(id)
   
    # ⭐ Track Recently Viewed
    if "user_id" in session:
        view = RecentlyViewed(
            user_id=session["user_id"],
            product_id=product.id
        )
        db.session.add(view)
        db.session.commit()

    reviews = Review.query.filter_by(
        product_id=id
    ).order_by(Review.id.desc()).all()

    # ---------- Images ----------
    images = []
    if product.image_url:
        images = [img.strip() for img in product.image_url.split(",")]

    # ---------- Similar Products (FIXED: 10) ----------
    similar_products = get_similar_products(product, top_n=10)

    if "user_id" in session:
        similar_products = rank_products_for_user(
            similar_products,
            session["user_id"]
        )

    # ---------- Customers Also Bought ----------
    also_bought_products = customers_also_bought(id)

    if "user_id" in session:
        also_bought_products = rank_products_for_user(
            also_bought_products,
            session["user_id"]
        )

    # ---------- Rating ----------
    total_reviews = len(reviews)

    avg_rating = db.session.query(func.avg(Review.rating))\
        .filter(Review.product_id == id).scalar()

    avg_rating = round(avg_rating, 1) if avg_rating else 0

    rating_counts = {}
    for i in range(1, 6):
        rating_counts[i] = Review.query.filter_by(
            product_id=id,
            rating=i
        ).count()

    return render_template(
        "product_details.html",
        product=product,
        images=images,
        reviews=reviews,
        similar_products=similar_products,
        also_bought_products=also_bought_products,
        categories=get_categories(),
        avg_rating=avg_rating,
        total_reviews=total_reviews,
        rating_counts=rating_counts
    )


# PRODUCT RECOMMENDATION
# -------------------------------------------------
@app.route("/recommend/<int:pid>")
def recommend(pid):
    products = Product.query.all()

    if len(products) < 2:
        flash("Not enough products for recommendation", "warning")
        return redirect("/products")

    data = []
    for p in products:
        text = f"{p.name} {p.category or ''} {p.description or ''} {p.brand or ''} {p.tags or ''}"
        data.append({"id": p.id, "text": text})

    df = pd.DataFrame(data)

    if pid not in df["id"].values:
        flash("Product not found", "danger")
        return redirect("/products")

    tfidf = TfidfVectorizer(stop_words="english")
    tfidf_matrix = tfidf.fit_transform(df["text"])

    index = df.index[df["id"] == pid][0]
    similarity = cosine_similarity(tfidf_matrix[index], tfidf_matrix).flatten()

    df["score"] = similarity
    rec_ids = (
        df.sort_values("score", ascending=False)
        .iloc[1:6]["id"]
        .tolist()
    )

    recommended_products = Product.query.filter(
        Product.id.in_(rec_ids)
    ).all()

    current_product = Product.query.get_or_404(pid)

    return render_template(
        "recommend.html",
        product=current_product,
        products=recommended_products,
        categories=get_categories()
    )
def get_similar_products(product, top_n=10):
    products = Product.query.all()

    # Safety check
    if len(products) < 2:
        return []

    # Prepare data
    data = []
    for p in products:
        text = f"{p.name} {p.category or ''} {p.description or ''} {p.brand or ''} {p.tags or ''}"
        data.append({
            "id": p.id,
            "text": text
        })

    df = pd.DataFrame(data)

    # TF-IDF
    tfidf = TfidfVectorizer(stop_words="english")
    tfidf_matrix = tfidf.fit_transform(df["text"])

    # Check if product exists
    if product.id not in df["id"].values:
        return []

    # Get index of current product
    index = df.index[df["id"] == product.id][0]

    # Cosine similarity
    similarity = cosine_similarity(
        tfidf_matrix[index],
        tfidf_matrix
    ).flatten()

    df["score"] = similarity

    # Get top N similar products (excluding itself)
    similar_ids = (
        df.sort_values("score", ascending=False)
          .iloc[1:top_n + 1]["id"]
          .tolist()
    )

    # Return products
    return Product.query.filter(
        Product.id.in_(similar_ids)
    ).all()
# -------------------------------------------------



@app.route("/category/<category>")
def filter_by_category(category):
    products = Product.query.filter_by(category=category).all()
    return render_template(
        "products.html",
        products=products,
        selected_category=category,
        categories=get_categories()
    )

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return redirect("/products")

    products = Product.query.filter(
        Product.name.ilike(f"%{query}%") |
        Product.category.ilike(f"%{query}%") |
        Product.brand.ilike(f"%{query}%") |
        Product.tags.ilike(f"%{query}%")
    ).all()

    return render_template(
        "products.html",
        products=products,
        search_query=query,
        categories=get_categories()
    )
# -------------------------------------------------
# CART
# -------------------------------------------------
@app.route("/cart")
def cart():
    if "user_id" not in session:
        return redirect("/login")

    cart_items = (
        db.session.query(Cart, Product)
        .join(Product, Cart.product_id == Product.id)
        .filter(Cart.user_id == session["user_id"])
        .all()
    )

    total = sum(p.price * c.quantity for c, p in cart_items)

    return render_template(
        "cart.html",
        cart_items=cart_items,
        total=total,
        categories=get_categories()
    )
@app.route("/remove/<int:pid>")
def remove_from_cart(pid):
    if "user_id" not in session:
        return redirect("/login")

    item = Cart.query.filter_by(
        user_id=session["user_id"],
        product_id=pid
    ).first()

    if item:
        db.session.delete(item)
        db.session.commit()

    return redirect("/cart")
@app.route("/update-cart/<int:pid>/<action>")
def update_cart(pid, action):
    if "user_id" not in session:
        return redirect("/login")

    item = Cart.query.filter_by(
        user_id=session["user_id"],
        product_id=pid
    ).first()

    if item:
        if action == "increase":
            item.quantity += 1
        elif action == "decrease" and item.quantity > 1:
            item.quantity -= 1

        db.session.commit()

    return redirect("/cart")
@app.route("/save-address", methods=["POST"])
@login_required
def save_checkout_address():

    name = request.form.get("name")
    phone = request.form.get("phone")
    address = request.form.get("address")
    city = request.form.get("city")
    pincode = request.form.get("pincode")

    # Future: Save to DB

    flash("Address saved successfully!", "success")

    return redirect(url_for("checkout"))


@app.route("/add__to_cart/<int:pid>")
def add_to_cart(pid):
    if "user_id" not in session:
        return redirect("/login")

    item = Cart.query.filter_by(
        user_id=session["user_id"],
        product_id=pid
    ).first()

    if item:
        item.quantity += 1
    else:
        db.session.add(Cart(
            user_id=session["user_id"],
            product_id=pid,
            quantity=1
        ))

    db.session.commit()
    flash("Product added to cart", "success")
    return redirect("/cart")


@app.route("/wishlist/add/<int:pid>")
@login_required
def add_to_wishlist(pid):
    user_id = session.get("user_id")

    exists = Wishlist.query.filter_by(
        user_id=user_id,
        product_id=pid
    ).first()

    if exists:
        flash("Already in wishlist", "info")
        return redirect(request.referrer or "/")

    wish = Wishlist(
        user_id=user_id,
        product_id=pid
    )

    db.session.add(wish)
    db.session.commit()

    flash("Added to wishlist ❤️", "success")
    return redirect(request.referrer or "/")

@app.route("/buy-now/<int:pid>", methods=["POST"])
@login_required
def buy_now(pid):
    product = Product.query.get_or_404(pid)
    order = razorpay_client.order.create({
        "amount": int(product.price * 100),
        "currency": "INR",
        "payment_capture": 1
    })
    return render_template(
        "payment.html",
        order=order,
        product=product
    )
@app.route("/add_review/<int:product_id>", methods=["POST"])
@login_required  # if you have login system
def add_review(product_id):

    rating = int(request.form["rating"])
    comment = request.form["comment"]

    review = Review(
        user_id=session["user_id"],
        product_id=product_id,
        rating=rating,
        comment=comment
    )

    db.session.add(review)
    db.session.commit()

    return redirect(url_for("product_details", id=product_id))
@app.route("/wishlist")
@login_required
def wishlist():

    user_id = session["user_id"]

    wishlist_items = (
        db.session.query(Wishlist, Product)
        .join(Product, Wishlist.product_id == Product.id)
        .filter(Wishlist.user_id == user_id)
        .all()
    )

    return render_template(
        "wishlist.html",
        wishlist_items=wishlist_items
    )
@app.route("/checkout")
@login_required
def checkout():

    cart_items = Cart.query.filter_by(user_id=session["user_id"]).all()

    total = 0
    valid_items = []

    for item in cart_items:
        product = db.session.get(Product, item.product_id)


        if product is None:
            continue

        total += product.price * item.quantity
        valid_items.append((item, product))

    if not valid_items:
        flash("Cart is empty", "warning")
        return redirect("/cart")

    return render_template(
        "checkout.html",
        cart_items=valid_items,
        total=total
    )
# ================= PAYMENT PAGE =================
@app.route("/payment")
@login_required
def payment():

    cart_items = (
        db.session.query(Cart, Product)
        .join(Product, Cart.product_id == Product.id)
        .filter(Cart.user_id == session["user_id"])
        .all()
    )

    total = sum(p.price * c.quantity for c, p in cart_items)

    return render_template(
        "payment.html",
        cart_items=cart_items,
        total=total,
        categories=get_categories()
    )

#------------------------------------------------
@app.route("/create_order", methods=["POST"])
@login_required
def create_order():

    user_id = session["user_id"]

    # Get cart items from database
    cart_items = Cart.query.filter_by(user_id=user_id).all()

    if not cart_items:
        return jsonify({"error": "Cart empty"}), 400

    total = 0

    for item in cart_items:
        # product = Product.query.get(item.product_id)
        product = db.session.get(Product, item.product_id)


        if product:
            total += product.price * item.quantity

    order_data = {
        "amount": int(total * 100),  # convert to paise
        "currency": "INR",
        "payment_capture": 1
    }

    razorpay_order = razorpay_client.order.create(order_data)

    return jsonify({
        "order_id": razorpay_order["id"],
        "amount": order_data["amount"]
    })

@app.route("/verify_payment", methods=["POST"])
@login_required
def verify_payment():

    data = request.json

    razorpay_payment_id = data.get("razorpay_payment_id")

    if razorpay_payment_id:
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "failed"}), 400

@app.route("/payment_success")
@login_required
def payment_success():

    print("SESSION DATA:", session)

    user_id = session["user_id"]
    user = db.session.get(User, user_id)

    # ---------------- SHIPPING ----------------
    shipping = session.get("shipping")

    if not shipping:
        shipping = {
            "full_name": user.name,
            "phone": "",
            "address": "",
            "city": "",
            "pincode": ""
        }

    cart_items = Cart.query.filter_by(user_id=user_id).all()

    total = 0
    for item in cart_items:
        product = db.session.get(Product, item.product_id)
        if product:
            total += product.price * item.quantity

    # ---------------- INVOICE ----------------
    year = datetime.now().year
    order_count = Order.query.count() + 1
    invoice_number = f"INV-{year}-{order_count:04d}"

    order = Order(
        invoice_number=invoice_number,
        user_id=user_id,
        total_amount=total,
        payment_method="UPI",
        status="Paid",
        full_name=shipping["full_name"],
        phone=shipping["phone"],
        address=shipping["address"],
        city=shipping["city"],
        pincode=shipping["pincode"]
    )

    db.session.add(order)
    db.session.commit()

    # ---------------- SAVE ORDER ITEMS ----------------
    for item in cart_items:
        product = db.session.get(Product, item.product_id)

        if product:
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item.quantity,
                price=product.price
            )
            db.session.add(order_item)

    db.session.commit()

    # ===============================
    # ⭐ AI EMAIL RECOMMENDATION
    # ===============================

    email_products = get_email_recommendations(user_id)

    try:
        msg = Message(
            subject="Order Confirmed ✅",
            sender=app.config["MAIL_USERNAME"],
            recipients=[user.email]
        )

        # -------- TEXT EMAIL --------
        msg.body = f"""
Hello {user.name},

Your Order {order.invoice_number} has been confirmed.

Total Amount: ₹{order.total_amount}
Payment Method: {order.payment_method}
Status: {order.status}

Thank you for shopping with us ❤️
"""

        # -------- HTML EMAIL --------
        msg.html = render_template(
            "order_email.html",
            order=order,
            email_products=email_products,
            user=user
        )

        mail.send(msg)
        print("Email sent successfully")

    except Exception as e:
        print("Email sending failed:", e)

    # ---------------- CLEAR CART ----------------
    Cart.query.filter_by(user_id=user_id).delete()
    db.session.commit()

    return render_template(
        "payment_success.html",
        order=order,
        email_products=email_products
    )


@app.route("/invoice/<int:order_id>")
def generate_invoice(order_id):

    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from datetime import datetime
    import os

    order = Order.query.get_or_404(order_id)
    items = OrderItem.query.filter_by(order_id=order.id).all()

    file_path = f"invoice_{order.invoice_number}.pdf"
    doc = SimpleDocTemplate(file_path)
    elements = []
    styles = getSampleStyleSheet()

    # 🔥 WATERMARK
    elements.append(Paragraph("<font size=60 color=lightgrey><b>PAID</b></font>", styles["Normal"]))
    elements.append(Spacer(1, 0.2 * inch))

    # 🔷 Company Header
    elements.append(Paragraph("<font size=18 color=darkblue><b>My Store Pvt Ltd</b></font>", styles["Title"]))
    elements.append(Paragraph("Satara, Maharashtra, India", styles["Normal"]))
    elements.append(Paragraph("Email: officialstore@gmail.com", styles["Normal"]))
    elements.append(Spacer(1, 0.3 * inch))

    # 🔷 Invoice Info
    elements.append(Paragraph(f"<b>Invoice Number:</b> {order.invoice_number}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Payment Method:</b> {order.payment_method}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Status:</b> {order.status}", styles["Normal"]))
    elements.append(Spacer(1, 0.3 * inch))

    # 🔷 Customer Info
    elements.append(Paragraph("<b>Bill To:</b>", styles["Heading3"]))
    elements.append(Paragraph(order.full_name, styles["Normal"]))
    elements.append(Paragraph(order.phone, styles["Normal"]))
    elements.append(Paragraph(f"{order.address}, {order.city} - {order.pincode}", styles["Normal"]))
    elements.append(Spacer(1, 0.3 * inch))

    # 🔷 Product Table
    data = [["Product", "Qty", "Price", "Subtotal"]]

    for item in items:
        product = db.session.get(Product, item.product_id)
        subtotal = item.quantity * item.price

        data.append([
            product.name,
            item.quantity,
            f"₹{item.price}",
            f"₹{subtotal}"
        ])

    data.append(["", "", "Total", f"₹{order.total_amount}"])

    table = Table(data, colWidths=[2.5*inch, inch, inch, inch])

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('BACKGROUND', (-2, -1), (-1, -1), colors.HexColor("#D9E1F2"))
    ]))

    elements.append(table)
    elements.append(Spacer(1, 0.5 * inch))

    elements.append(Paragraph("Thank you for shopping with us ❤️", styles["Normal"]))

    doc.build(elements)

    return send_file(file_path, as_attachment=True)
@app.route("/my-orders")
@login_required
def user_orders():
    orders = Order.query.filter_by(
        user_id=session["user_id"]
    ).order_by(Order.id.desc()).all()

    return render_template("user_orders.html", orders=orders)
@app.route("/track/<int:order_id>")
@login_required
def track_order(order_id):
    order = db.session.get(Order, order_id)
    return render_template("order_tracking.html", order=order)
# ---------------------------------------
# USER ORDER HISTORY PAGE
# ---------------------------------------
@app.route("/user_order")
@login_required
def user_order():

    user = db.session.get(User, session["user_id"])

    orders = Order.query.filter_by(
        user_id=session["user_id"]
    ).order_by(Order.id.desc()).all()

    total_orders = len(orders)

    return render_template(
        "user_order.html",
        orders=orders,
        user=user,
        total_orders=total_orders
    )
@app.route("/order/<int:order_id>")
@login_required
def order_detail(order_id):

    order = db.session.get(Order, order_id)

    # Security check →
    if order.user_id != session["user_id"]:
        flash("Unauthorized access", "danger")
        return redirect("/user_order")

    order_items = (
        db.session.query(OrderItem, Product)
        .join(Product, OrderItem.product_id == Product.id)
        .filter(OrderItem.order_id == order_id)
        .all()
    )

    return render_template(
        "order_detail.html",
        order=order,
        order_items=order_items,
        categories=get_categories()
    )


if __name__ == "__main__":
    app.run(debug=True)  
