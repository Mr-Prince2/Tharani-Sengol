import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
import joblib
import os

def train_and_export():
    dataset_path = "trichy_vehicle_dataset.csv"
    if not os.path.exists(dataset_path):
        print("Dataset not found. Please run dataset_gen.py first.")
        return
        
    print("Loading dataset...")
    df = pd.read_csv(dataset_path)
    
    # Feature Engineering
    features = ['speed', 'trip_count', 'route_deviation', 'gps_signal_loss', 
                'time_of_day', 'day_of_week', 'risk_score']
    
    X = df[features]
    y = df['violation_label']
    
    # Train / Test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("Training RandomForest model... This might take a moment.")
    # Hyperparameter tuning (basic)
    model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
    model.fit(X_train, y_train)
    
    # Accuracy evaluation
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"Model Accuracy on Test Set: {accuracy * 100:.2f}%")
    print("Classification Report:")
    print(classification_report(y_test, y_pred))
    
    from sklearn.metrics import confusion_matrix
    print("Confusion Matrix:")
    print(confusion_matrix(y_test, y_pred))
    
    # Export model
    model_name = "illegal_mining_rf.pkl"
    joblib.dump(model, model_name)
    print(f"Model saved as {model_name} successfully.")
    
if __name__ == "__main__":
    train_and_export()
