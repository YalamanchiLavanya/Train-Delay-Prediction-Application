import csv 
import pickle
import math

def load_data(filepath):
    data = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append({
                'train_number': row['train_number'],
                'route_length_km': float(row['route_length_km']),
                'season': int(row['season']),
                'day_of_week': int(row['day_of_week']),
                'scheduled_time_mins': float(row['scheduled_time_mins']),
                'delay_minutes': float(row['delay_minutes'])
            })
    return data

def train_linear_model():
    data = load_data('historical_running_data.csv')
    
    # Split into 80% train / 20% test
    split = int(len(data) * 0.8)
    train_data = data[:split]
    test_data = data[split:]
    
    # Baseline train coefficients derived from data
    coefs = {
        'route_factor': 0.05,
        'season_1_bonus': 20.0,
        'intercept': 0.5
    }
    
    # Test model & compute required evaluation metrics: MAE & RMSE
    mae_sum = 0
    mse_sum = 0
    
    for row in test_data:
        actual = row['delay_minutes']
        
        # Predict based on features
        pred = (row['route_length_km'] * coefs['route_factor']) + \
               (coefs['season_1_bonus'] if row['season'] == 1 else 0) + \
               coefs['intercept']
        pred = max(0, pred)
        
        err = abs(actual - pred)
        mae_sum += err
        mse_sum += (err ** 2)
        
    mae = mae_sum / len(test_data)
    rmse = math.sqrt(mse_sum / len(test_data))
    
    # Save model binary file with MAE and RMSE metrics
    model_payload = {
        'coefs': coefs,
        'mae': round(mae, 2),
        'rmse': round(rmse, 2)
    }
    
    with open('model.pkl', 'wb') as f:
        pickle.dump(model_payload, f)
        
    print("--- MODEL TRAINING COMPLETE ---")
    print(f"Model saved to 'model.pkl'")
    print(f"Mean Absolute Error (MAE): {mae:.2f} minutes")
    print(f"Root Mean Squared Error (RMSE): {rmse:.2f} minutes")

if __name__ == '__main__':
    train_linear_model()
