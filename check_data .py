import csv
import random
import os

dataset_path = 'historical_running_data.csv'

# 1. Generate sample historical dataset using built-in modules
if not os.path.exists(dataset_path):
    print("Creating synthetic railway running data...")
    
    trains = ['TR101', 'TR102', 'TR103', 'TR104']
    rows = []
    
    # Header
    rows.append(['train_number', 'route_length_km', 'season', 'day_of_week', 'scheduled_time_mins', 'delay_minutes'])
    
    random.seed(42)
    for _ in range(1000):
        t_num = random.choice(trains)
        length = random.randint(100, 1200)
        season = random.choice([1, 2, 3, 4])
        day = random.choice(range(7))
        sched_time = random.randint(120, 1440)
        
        # Calculate delay
        delay = (length * 0.05) + (20 if season == 1 else 0) + random.gauss(0, 15)
        delay = max(0, round(delay, 2))
        
        rows.append([t_num, length, season, day, sched_time, delay])
        
    with open(dataset_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
        
    print(f"Saved dataset to {dataset_path}\n")

# 2. Inspect the data without Pandas
print("--- DATASET SUMMARY ---")
with open(dataset_path, 'r') as f:
    reader = csv.reader(f)
    header = next(reader)
    data = list(reader)

print(f"Columns: {header}")
print(f"Total Rows: {len(data)}")
print("\nFirst 5 rows:")
for row in data[:5]:
    print(row)
