// Water Quality Dashboard JavaScript

class WaterQualityDashboard {
    constructor() {
        this.updateInterval = 15000; // 15 seconds
        this.isUpdating = false;
        this.setupEventListeners();
        this.startAutoUpdate();
    }

    setupEventListeners() {
        document.addEventListener('DOMContentLoaded', () => {
            this.updateData();
        });
    }

    startAutoUpdate() {
        setInterval(() => this.updateData(), this.updateInterval);
    }

    async updateData() {
        if (this.isUpdating) return;
        this.isUpdating = true;

        try {
            const response = await fetch('/get_latest_data');
            const data = await response.json();

            if (data.success) {
                this.updateUI(data.data);
                this.updateIndicator(true);
            } else {
                this.updateIndicator(false);
                console.error('Failed to fetch data:', data.message);
            }
        } catch (error) {
            this.updateIndicator(false);
            console.error('Error updating data:', error);
        } finally {
            this.isUpdating = false;
        }
    }

    updateUI(data) {
        // Update parameter values
        this.updateParameter('ph', data.ph, 14);
        this.updateParameter('tds', data.tds, 2000);
        this.updateParameter('turbidity', data.turbidity, 50);

        // Update WQI values
        this.updateWQI('formula', data.wqi_formula, data.formula_grade);
        this.updateWQI('model', data.wqi_predicted, data.model_grade);

        // Update timestamp
        document.getElementById('timestamp').textContent = data.timestamp;

        // Update visualization if needed
        if (data.plot_image) {
            document.getElementById('plotImage').src = `data:image/png;base64,${data.plot_image}`;
        }
    }

    updateParameter(name, value, max) {
        const valueElement = document.getElementById(`${name}Value`);
        const progressBar = document.querySelector(`.progress-bar-${name}`);
        
        if (valueElement && progressBar) {
            valueElement.textContent = value.toFixed(2);
            const percentage = (value / max) * 100;
            progressBar.style.width = `${Math.min(percentage, 100)}%`;
            
            // Update color based on value ranges
            this.updateParameterColor(progressBar, name, value);
        }
    }

    updateParameterColor(element, parameter, value) {
        let color;
        switch (parameter) {
            case 'ph':
                color = this.getPHColor(value);
                break;
            case 'tds':
                color = this.getTDSColor(value);
                break;
            case 'turbidity':
                color = this.getTurbidityColor(value);
                break;
        }
        element.style.backgroundColor = color;
    }

    getPHColor(value) {
        if (value < 6.5 || value > 8.5) return '#dc3545';
        if (value < 7.0 || value > 8.0) return '#ffc107';
        return '#28a745';
    }

    getTDSColor(value) {
        if (value > 1000) return '#dc3545';
        if (value > 500) return '#ffc107';
        return '#28a745';
    }

    getTurbidityColor(value) {
        if (value > 5) return '#dc3545';
        if (value > 1) return '#ffc107';
        return '#28a745';
    }

    updateWQI(type, value, grade) {
        const wqiElement = document.getElementById(`${type}WQI`);
        const gradeElement = document.getElementById(`${type}Grade`);
        
        if (wqiElement && gradeElement) {
            wqiElement.textContent = value.toFixed(2);
            gradeElement.textContent = grade;
            
            // Update grade styling
            gradeElement.className = 'quality-grade ' + 
                (grade === 'A' ? 'grade-a' : 
                 grade === 'B' ? 'grade-b' : 'grade-c');
        }
    }

    updateIndicator(isActive) {
        const indicator = document.getElementById('realTimeIndicator');
        if (indicator) {
            indicator.className = `real-time-indicator ${isActive ? 'indicator-active' : 'indicator-inactive'}`;
        }
    }
}

// Initialize dashboard
const dashboard = new WaterQualityDashboard(); 