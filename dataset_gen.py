import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import os

# Trichy Bounding Box for realistic coordinates
TRICHY_BOUNDS = {
    "lat_min": 10.7500, "lat_max": 10.8800,
    "lon_min": 78.6500, "lon_max": 78.7800
}

def generate_dataset(num_rows=100000, output_file="trichy_vehicle_dataset.csv"):
    print(f"Generating synthetic dataset with {num_rows} rows...")
    data = []
    
    start_time = datetime.now() - timedelta(days=30)
    
    for i in range(num_rows):
        is_illegal = np.random.choice([0, 1], p=[0.7, 0.3]) # 30% illegal trips
        
        # Base logical parameters
        vehicle_id = f"truck_{random.randint(1, 50)}"
        timestamp = start_time + timedelta(minutes=random.randint(1, 43200)) # random time in last 30 days
        
        # Geo-location within Trichy
        lat = random.uniform(TRICHY_BOUNDS["lat_min"], TRICHY_BOUNDS["lat_max"])
        lon = random.uniform(TRICHY_BOUNDS["lon_min"], TRICHY_BOUNDS["lon_max"])
        
        if is_illegal:
            speed = random.uniform(50, 90) # Higher speeds at night for illegal mining
            trip_count = random.randint(8, 20) # Usually extra trips
            route_deviation = np.random.choice([0, 1], p=[0.2, 0.8])
            gps_signal_loss = np.random.choice([0, 1], p=[0.3, 0.7])
            risk_score = random.randint(50, 100) # High risk
        else:
            speed = random.uniform(20, 60) # Normal speed
            trip_count = random.randint(1, 7) # Normal trip count
            route_deviation = np.random.choice([0, 1], p=[0.95, 0.05])
            gps_signal_loss = np.random.choice([0, 1], p=[0.95, 0.05])
            risk_score = random.randint(0, 49) # Low risk
            
        time_of_day = timestamp.hour
        day_of_week = timestamp.weekday()
        
        data.append({
            "vehicle_id": vehicle_id,
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "speed": round(speed, 2),
            "trip_count": trip_count,
            "route_deviation": route_deviation,
            "gps_signal_loss": gps_signal_loss,
            "time_of_day": time_of_day,
            "day_of_week": day_of_week,
            "risk_score": risk_score,
            "violation_label": is_illegal
        })

    df = pd.DataFrame(data)
    df.to_csv(output_file, index=False)
    print(f"Dataset saved to {output_file} successfully.")
    
if __name__ == "__main__":
    generate_dataset()
