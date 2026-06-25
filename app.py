import uuid
import os
import secrets
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, jsonify

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from models import db, User, Property

app = Flask(__name__)

# CONFIG
app.config['SECRET_KEY'] = 'kejahunt-secret-key'

basedir = os.path.abspath(os.path.dirname(__file__))

app.config['SQLALCHEMY_DATABASE_URI'] = \
    'sqlite:///' + os.path.join(basedir, 'kejahunt.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(basedir, 'static/uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db.init_app(app)

# LOGIN MANAGER
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# CREATE DB
with app.app_context():
    db.create_all()


# HOME
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


# REGISTER
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        if User.query.filter_by(email=email).first():
            return "Email already exists."

        if User.query.filter_by(username=username).first():
            return "Username already exists."

        hashed_password = generate_password_hash(password)

        new_user = User(
            username=username,
            email=email,
            password=hashed_password,
            role=role
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('register.html')


# LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))

        return "Invalid email or password."

    return render_template('login.html')


# DASHBOARD ROUTER
@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == "landlord":
        return redirect(url_for('landlord_dashboard'))
    return redirect(url_for('user_dashboard'))


# USER DASHBOARD
@app.route('/user_dashboard')
@login_required
def user_dashboard():
    if current_user.role != "user":
        return redirect(url_for('dashboard'))
    return render_template(
        'dashboard/user_dashboard.html',
        user=current_user
    )


# LANDLORD DASHBOARD
@app.route('/landlord_dashboard')
@login_required
def landlord_dashboard():
    if current_user.role != "landlord":
        return redirect(url_for('dashboard'))
    return render_template(
        'dashboard/landlord_dashboard.html',
        user=current_user
    )


# LOGOUT
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


# =========================
# 🏠 PROPERTY SYSTEM STARTS
# =========================

# ADD PROPERTY
@app.route('/add_property', methods=['GET', 'POST'])
@login_required
def add_property():
    if current_user.role != "landlord":
        return "Only landlords can add properties."

    if request.method == 'POST':
        image = request.files['image']
        filename = None

        if image:
            filename = str(uuid.uuid4()) + "_" + secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        new_property = Property(
            title=request.form['title'],
            description=request.form['description'],
            price=request.form['price'],
            location=request.form['location'],
            bedrooms=request.form['bedrooms'],
            bathrooms=request.form['bathrooms'],
            image_file=filename,
            phone=request.form['phone'],
            landlord_id=current_user.id
        )

        db.session.add(new_property)
        db.session.commit()

        return redirect(url_for('my_properties'))

    return render_template('add_property.html')


# LANDLORD PROPERTIES
@app.route('/my_properties')
@login_required
def my_properties():
    if current_user.role != "landlord":
        return "Unauthorized"

    props = Property.query.filter_by(
        landlord_id=current_user.id
    ).all()

    return render_template(
        'my_properties.html',
        properties=props
    )


# =========================
# 🔍 SEARCH + PUBLIC LISTING
# =========================
@app.route('/properties')
def properties():
    query = request.args.get('q')

    if query:
        props = Property.query.filter(
            Property.title.contains(query) |
            Property.location.contains(query) |
            Property.description.contains(query)
        ).all()
    else:
        props = Property.query.all()

    return render_template(
        'properties.html',
        properties=props,
        query=query
    )


# PROPERTY DETAILS
@app.route('/property/<int:property_id>')
def property_details(property_id):
    prop = Property.query.get_or_404(property_id)
    return render_template(
        'property_details.html',
        property=prop
    )


# =========================
# 📱 MOBILE API ROUTES
# =========================

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    print("Register data received:", data)

    if not data:
        return jsonify({'message': 'No data received'}), 400

    email = data.get('email')
    full_name = data.get('full_name')
    phone = data.get('phone')
    password = data.get('password')
    role = data.get('role')

    if not email or not full_name or not password or not role:
        return jsonify({'message': 'Missing required fields'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'Email already exists'}), 400

    if User.query.filter_by(username=email).first():
        return jsonify({'message': 'User already exists'}), 400

    hashed_password = generate_password_hash(password)
    token = secrets.token_hex(16)

    new_user = User(
        username=email,
        email=email,
        password=hashed_password,
        role=role,
        token=token
    )

    db.session.add(new_user)
    db.session.commit()

    return jsonify({
        'message': 'Registered successfully',
        'role': role,
        'full_name': full_name,
        'email': email,
        'token': token
    }), 201

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    print("Login data received:", data)

    if not data:
        return jsonify({'message': 'No data received'}), 400

    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password, password):
        return jsonify({'message': 'Invalid credentials'}), 401

    token = secrets.token_hex(16)
    user.token = token
    db.session.commit()

    return jsonify({
        'message': 'Login successful',
        'role': user.role,
        'full_name': user.username,
        'email': user.email,
        'token': token
    }), 200


@app.route('/api/properties', methods=['GET'])
def get_properties():
    properties = Property.query.all()
    result = []
    for p in properties:
        landlord = User.query.get(p.landlord_id)
        result.append({
            'id': p.id,
            'title': p.title,
            'location': p.location,
            'price': str(p.price),
            'description': p.description,
            'image_url': p.image_file,
            'landlord_name': landlord.username if landlord else 'Unknown',
            'landlord_id': p.landlord_id
        })
    return jsonify(result)


@app.route('/api/properties', methods=['POST'])
def api_post_property():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    user = User.query.filter_by(token=token).first()

    if not user or user.role != 'landlord':
        return jsonify({'message': 'Unauthorized'}), 401

    title = request.form.get('title')
    location = request.form.get('location')
    price = request.form.get('price')
    description = request.form.get('description')
    property_type = request.form.get('property_type')

    filename = None
    if 'image' in request.files:
        image = request.files['image']
        if image.filename != '':
            filename = str(uuid.uuid4()) + "_" + secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    new_property = Property(
        title=title,
        location=location,
        price=price,
        description=description,
        property_type=property_type,
        landlord_id=user.id,
        phone='',
        bedrooms=0,
        bathrooms=0,
        image_file=filename
    )

    db.session.add(new_property)
    db.session.commit()

    return jsonify({'message': 'Property posted successfully'}), 201


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)