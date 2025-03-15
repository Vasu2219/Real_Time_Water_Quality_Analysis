from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from flask_migrate import Migrate
import numpy as np
import joblib
import requests
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Set the backend to 'Agg' before importing pyplot
import matplotlib.pyplot as plt
import seaborn as sns
import base64
from io import BytesIO
import time
from datetime import datetime, timedelta
from flask_login import login_user, login_required, current_user, LoginManager, UserMixin, logout_user

app = Flask(__name__)

# Use environment variable for secret key
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['ADMIN_KEY'] = 'Vasu@123'

# ThingSpeak configuration
THINGSPEAK_CHANNEL_ID = "2845308"  # Replace with your channel ID
THINGSPEAK_READ_API_KEY = "7K0QBM6EM1OV910C"    # Replace with your API key
THINGSPEAK_URL = f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds/last.json"

# Load ML model and scaler
MODEL_PATH = "D:/Clean_Green/wqi_model.pkl"
SCALER_PATH = "D:/Clean_Green/scaler.pkl"

try:
    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
except Exception as e:
    print(f"Error loading model or scaler: {e}")
    model = None
    scaler = None

# Initialize Flask extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<User {self.username}>'

class WQIConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parameter = db.Column(db.String(50), nullable=False)
    min_value = db.Column(db.Float, nullable=False)
    max_value = db.Column(db.Float, nullable=False)
    weight = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    def __repr__(self):
        return f'<WQIConfig {self.parameter}>'

def init_default_config():
    with app.app_context():
        if not WQIConfig.query.first():
            default_configs = [
                WQIConfig(parameter='ph_normal', min_value=7.0, max_value=8.0, weight=0.4),
                WQIConfig(parameter='ph_acidic', min_value=6.5, max_value=7.0, weight=0.5),
                WQIConfig(parameter='ph_alkaline', min_value=8.0, max_value=8.5, weight=0.5),
                WQIConfig(parameter='tds_normal', min_value=0, max_value=500, weight=0.3),
                WQIConfig(parameter='tds_high', min_value=500, max_value=1000, weight=0.4),
                WQIConfig(parameter='turbidity_normal', min_value=0, max_value=1, weight=0.3),
                WQIConfig(parameter='turbidity_high', min_value=1, max_value=5, weight=0.4)
            ]
            for config in default_configs:
                db.session.add(config)
            db.session.commit()

def get_current_config():
    configs = WQIConfig.query.all()
    config_dict = {}
    for config in configs:
        config_dict[config.parameter] = {
            'min_value': config.min_value,
            'max_value': config.max_value,
            'weight': config.weight
        }
    return config_dict

def calculate_wqi(ph, tds, turbidity):
    configs = get_current_config()
    
    # Calculate individual parameter scores with dynamic ranges
    def get_ph_score(ph):
        if ph < configs['ph_acidic']['min_value'] or ph > configs['ph_alkaline']['max_value']:
            return 0
        elif configs['ph_normal']['min_value'] <= ph <= configs['ph_normal']['max_value']:
            return 100
        else:
            return 80

    def get_tds_score(tds):
        if tds > configs['tds_high']['max_value']:
            return 0
        elif tds <= configs['tds_normal']['max_value']:
            return 100
        else:
            return 80 - ((tds - configs['tds_normal']['max_value']) * 0.1)

    def get_turbidity_score(turbidity):
        if turbidity > configs['turbidity_high']['max_value']:
            return 0
        elif turbidity <= configs['turbidity_normal']['max_value']:
            return 100
        else:
            return 80 - ((turbidity - configs['turbidity_normal']['max_value']) * 20)

    # Calculate scores
    ph_score = get_ph_score(ph)
    tds_score = get_tds_score(tds)
    turbidity_score = get_turbidity_score(turbidity)

    # Determine weights based on conditions using dynamic config
    if ph < configs['ph_acidic']['min_value'] or ph > configs['ph_alkaline']['max_value']:
        weights = {
            'ph': configs['ph_acidic']['weight'],
            'tds': configs['tds_normal']['weight'],
            'turbidity': configs['turbidity_normal']['weight']
        }
    elif tds > configs['tds_high']['max_value']:
        weights = {
            'ph': configs['ph_normal']['weight'],
            'tds': configs['tds_high']['weight'],
            'turbidity': configs['turbidity_normal']['weight']
        }
    elif turbidity > configs['turbidity_high']['max_value']:
        weights = {
            'ph': configs['ph_normal']['weight'],
            'tds': configs['tds_normal']['weight'],
            'turbidity': configs['turbidity_high']['weight']
        }
    else:
        weights = {
            'ph': configs['ph_normal']['weight'],
            'tds': configs['tds_normal']['weight'],
            'turbidity': configs['turbidity_normal']['weight']
        }

    # Calculate WQI
    wqi = (
        ph_score * weights['ph'] +
        tds_score * weights['tds'] +
        turbidity_score * weights['turbidity']
    )

    return wqi

def get_wqi_grade(wqi):
    if wqi >= 80:
        return 'A'
    elif wqi >= 60:
        return 'B'
    else:
        return 'C'

def create_visualization(ph, tds, turbidity, wqi_formula, wqi_predicted):
    # Create figure with a light background
    plt.clf()  # Clear any existing plots
    fig = plt.figure(figsize=(12, 6))
    
    # Create subplots with adjusted layout
    gs = plt.GridSpec(2, 2, figure=fig)
    
    # Parameter values plot
    ax1 = fig.add_subplot(gs[0, 0])
    params = ['pH', 'TDS', 'Turbidity']
    values = [ph, tds/100, turbidity]  # Normalize TDS for better visualization
    colors = ['#17a2b8', '#28a745', '#ffc107']
    
    bars = ax1.bar(params, values, color=colors)
    ax1.set_title('Current Parameter Values', pad=15)
    ax1.set_ylim(0, max(values) * 1.2)
    
    # Add value labels
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}', ha='center', va='bottom')
    
    # WQI Comparison
    ax2 = fig.add_subplot(gs[0, 1])
    wqi_values = [wqi_formula, wqi_predicted]
    wqi_labels = ['Formula WQI', 'ML Model WQI']
    
    bars = ax2.bar(wqi_labels, wqi_values, color=['#007bff', '#6f42c1'])
    ax2.set_title('WQI Comparison', pad=15)
    ax2.set_ylim(0, 100)
    
    # Add value labels
    for bar in bars:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}', ha='center', va='bottom')
    
    # Parameter ranges plot
    ax3 = fig.add_subplot(gs[1, :])
    
    # Define ideal ranges
    ranges = {
        'pH': (6.5, 8.5),
        'TDS (mg/L)': (0, 1000),
        'Turbidity (NTU)': (0, 5)
    }
    
    current_values = {
        'pH': ph,
        'TDS (mg/L)': tds,
        'Turbidity (NTU)': turbidity
    }
    
    y_pos = np.arange(len(ranges))
    
    # Plot ranges
    for i, (param, (min_val, max_val)) in enumerate(ranges.items()):
        ax3.barh(i, max_val - min_val, left=min_val, color='#e9ecef', height=0.3)
        # Plot current value
        current_val = current_values[param]
        ax3.plot(current_val, i, 'ro')
        
    ax3.set_yticks(y_pos)
    ax3.set_yticklabels(ranges.keys())
    ax3.set_title('Parameter Ranges (Red Dots: Current Values)', pad=15)
    
    # Adjust layout with specific padding
    fig.set_tight_layout(True)
    plt.subplots_adjust(top=0.95, bottom=0.1, hspace=0.3)
    
    # Convert plot to base64 string
    buffer = BytesIO()
    fig.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
    buffer.seek(0)
    image_png = buffer.getvalue()
    buffer.close()
    plt.close(fig)  # Explicitly close the figure
    
    return base64.b64encode(image_png).decode('utf-8')

def fetch_thingspeak_data():
    try:
        response = requests.get(THINGSPEAK_URL, params={'api_key': THINGSPEAK_READ_API_KEY})
        if response.status_code == 200:
            data = response.json()
            return {
                'ph': float(data['field1']),
                'tds': float(data['field2']),
                'turbidity': float(data['field3']),
                'timestamp': data['created_at']
            }
        else:
            return None
    except Exception as e:
        print(f"Error fetching ThingSpeak data: {e}")
        return None

# Routes
@app.route('/')
def index():
    username = session.get('username')
    return render_template('index.html', username=username)

@app.route('/water_quality')
@login_required
def water_quality():
    return render_template('water_quality.html', 
                         loading=True,
                         prediction_made=False)

@app.route('/get_latest_data')
@login_required
def get_latest_data():
    """API endpoint for getting latest sensor data"""
    data = fetch_thingspeak_data()
    if data:
        ph = data['ph']
        tds = data['tds']
        turbidity = data['turbidity']
        
        wqi_formula = calculate_wqi(ph, tds, turbidity)
        formula_grade = get_wqi_grade(wqi_formula)
        
        if model and scaler:
            input_scaled = scaler.transform([[ph, tds, turbidity]])
            wqi_predicted = model.predict(input_scaled)[0]
            model_grade = get_wqi_grade(wqi_predicted)
        else:
            wqi_predicted = wqi_formula
            model_grade = formula_grade
        
        # Create visualization
        plot_image = create_visualization(ph, tds, turbidity, wqi_formula, wqi_predicted)
        
        return jsonify({
            'success': True,
            'data': {
                'ph': ph,
                'tds': tds,
                'turbidity': turbidity,
                'wqi_formula': wqi_formula,
                'formula_grade': formula_grade,
                'wqi_predicted': wqi_predicted,
                'model_grade': model_grade,
                'plot_image': plot_image,
                'timestamp': data['timestamp']
            }
        })
    
    return jsonify({'success': False, 'message': 'Could not fetch sensor data'})

# Existing routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('water_quality'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        is_admin = request.form.get('is_admin') == 'on'
        admin_key = request.form.get('admin_key')

        if not username or not password:
            flash('Username and password are required', 'error')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))

        if is_admin:
            if not admin_key or admin_key != app.config['ADMIN_KEY']:
                flash('Invalid admin registration key', 'error')
                return redirect(url_for('register'))

        try:
            hashed_password = generate_password_hash(password)
            new_user = User(username=username, password=hashed_password, is_admin=is_admin)
            db.session.add(new_user)
            db.session.commit()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Error during registration. Please try again.', 'error')
            print(f"Registration error: {str(e)}")
            return render_template('register.html')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('water_quality'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please provide both username and password', 'error')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('water_quality'))
        
        flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('index'))
    
    configs = WQIConfig.query.all()
    users = User.query.all()
    return render_template('admin_dashboard.html', configs=configs, users=users)

@app.route('/admin/update_config', methods=['POST'])
@login_required
def update_config():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        config_id = request.form.get('config_id', type=int)
        min_value = request.form.get('min_value', type=float)
        max_value = request.form.get('max_value', type=float)
        weight = request.form.get('weight', type=float)
        
        if None in [config_id, min_value, max_value, weight]:
            return jsonify({'success': False, 'message': 'Invalid parameters'})
        
        config = WQIConfig.query.get(config_id)
        if not config:
            return jsonify({'success': False, 'message': 'Configuration not found'})
        
        config.min_value = min_value
        config.max_value = max_value
        config.weight = weight
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Configuration updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        if user.id == current_user.id:
            return jsonify({'success': False, 'message': 'Cannot delete your own account'})
        
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'User deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def init_db():
    with app.app_context():
        db.create_all()
        
        # Create default admin user if not exists
        admin = User.query.filter_by(username='Vasu').first()
        if not admin:
            admin = User(username='Vasu', password=generate_password_hash('Vasu@2219'), is_admin=True)
            db.session.add(admin)
        
        # Create default WQI configurations if not exist
        default_configs = [
            {'parameter': 'pH', 'min_value': 6.5, 'max_value': 8.5, 'weight': 0.2},
            {'parameter': 'DO', 'min_value': 4.0, 'max_value': 8.0, 'weight': 0.2},
            {'parameter': 'BOD', 'min_value': 0.0, 'max_value': 6.0, 'weight': 0.2},
            {'parameter': 'Temperature', 'min_value': 20.0, 'max_value': 30.0, 'weight': 0.1},
            {'parameter': 'Turbidity', 'min_value': 0.0, 'max_value': 5.0, 'weight': 0.15},
            {'parameter': 'TDS', 'min_value': 0.0, 'max_value': 1000.0, 'weight': 0.15}
        ]
        
        for config in default_configs:
            if not WQIConfig.query.filter_by(parameter=config['parameter']).first():
                new_config = WQIConfig(**config)
                db.session.add(new_config)
        
        db.session.commit()

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
