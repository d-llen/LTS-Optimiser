import sys
import os
import glob
import re
import time
import csv
from datetime import datetime
from scipy.optimize import minimize
# terminal cmds: 
# cd "C:\Users\dille\OneDrive - University of Warwick\Physics\Y3\WR\CM"

# Capture the exact directory where THIS Python script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ==========================================
# --- 1. Hooking into the ASAM XIL API ---
# ==========================================
CARMAKER_PYTHON_DIR = r"C:\IPG\carmaker\win64-14.1.1\Python\python3.12"
sys.path.append(CARMAKER_PYTHON_DIR)

from ASAM.XIL.Implementation.Testbench import TestbenchFactory
from ASAM.XIL.Interfaces.Testbench.MAPort.Enum.MAPortState import MAPortState

PROJECT_DIR  = r"C:\CM_Projects\FS_LTS_2025_v1"
TESTRUN_FILE = "FS_Sprint_2025" 

# List of all baseline vehicles
BASELINE_VEHICLES = [
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Aero_1EM_Locked.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Aero_1EM_Open.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Aero_1EM_Torsen.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Aero_4EM.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Aero_NA_Locked.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Aero_NA_Open.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Aero_NA_Torsen.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Aero_Turbo_Locked.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Aero_Turbo_Open.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Aero_Turbo_Torsen.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Naero_1EM_Locked.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Naero_1EM_Open.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Naero_1EM_Torsen.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Naero_4EM.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Naero_NA_Locked.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Naero_NA_open.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Naero_NA_torsen.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Naero_Turbo_Locked.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Naero_Turbo_Open.car",
    r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Naero_Turbo_Torsen.car",
]

# ==========================================
# --- 2. Menu Selection System ---
# ==========================================
def select_vehicle():
    print("\n" + "="*50)
    print(" BASELINE VEHICLE SELECTION")
    print("="*50)
    
    for i, path in enumerate(BASELINE_VEHICLES):
        car_name = os.path.basename(path)
        print(f" {i+1:2d} - {car_name}")
        
    print("="*50)
    
    while True:
        try:
            choice = int(input("\nEnter the number of the vehicle to test (1-20): "))
            if 1 <= choice <= len(BASELINE_VEHICLES):
                selected_path = BASELINE_VEHICLES[choice-1]
                car_name = os.path.basename(selected_path).replace('.car', '')
                print(f"\n[+] Selected: {car_name}")
                
                input("\n[!] IMPORTANT: Make sure you have saved the TestRun in CarMaker GUI with this vehicle and run a Race Driver Adaptation! Press ENTER to continue...")
                return selected_path, car_name
            else:
                print("Invalid selection. Please enter a number between 1 and 20.")
        except ValueError:
            print("Please enter a valid number.")

# ==========================================
# --- 3. CSV Logging Class ---
# ==========================================
class CSVLogger:
    def __init__(self, script_dir, vehicle_name):
        # 1. Generate the datestamped folder name (e.g., Results_2026-02-26)
        date_stamp = datetime.now().strftime("%Y-%m-%d")
        self.log_folder = os.path.join(script_dir, f"Results_{date_stamp}")
        
        # 2. Create the directory safely
        os.makedirs(self.log_folder, exist_ok=True)
        
        # 3. Create the timestamped file name
        time_stamp = datetime.now().strftime("%H%M%S")
        self.filename = os.path.join(self.log_folder, f"Optimization_{vehicle_name}_{time_stamp}.csv")
        
        self.headers = ["Front Spring [N/m]", "Rear Spring [N/m]", "Raw Lap Time [s]", "Cones Hit", "Total Time [s]"]
        with open(self.filename, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(self.headers)
        
        print(f"\n[LOG] Created directory: {self.log_folder}")
        print(f"[LOG] Results will be saved to: {self.filename}")

    def log_run(self, front_k, rear_k, raw_time, cones, total_time):
        with open(self.filename, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([front_k, rear_k, raw_time, cones, total_time])

# ==========================================
# --- 4. Helper Functions ---
# ==========================================
def modify_vehicle_parameters(file_path, params_dict):
    with open(file_path, 'r') as file:
        file_data = file.read()

    for param_name, new_value in params_dict.items():
        pattern = rf"({param_name}\s*=\s*)[0-9.-]+"
        replacement = rf"\g<1>{new_value:.1f}"
        file_data = re.sub(pattern, replacement, file_data)

    with open(file_path, 'w') as file:
        file.write(file_data)

def get_latest_results_file():
    time.sleep(1.0) 
    search_pattern = os.path.join(PROJECT_DIR, "SimOutput", "**", "Log", "*.log")
    list_of_files = glob.glob(search_pattern, recursive=True)
    if not list_of_files:
        raise FileNotFoundError("Could not find any .log files!")
    return max(list_of_files, key=os.path.getmtime)

def extract_lap_data(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        matches = re.findall(r'Lap\s*Time\s*=\s*([\d.]+)\s*Cones\s*hit\s*=\s*(\d+)', content, re.IGNORECASE)
        
        if matches:
            latest_match = matches[-1]
            raw_time = float(latest_match[0])
            cones = int(latest_match[1])
            total_time = raw_time + (cones * 2.0)
            return raw_time, cones, total_time
        else:
            return 999.0, 0, 999.0
            
    except Exception as e:
        print(f"   [!] Error extracting data: {e}")
        return 999.0, 0, 999.0

# ==========================================
# --- 5. The XIL API Bridge ---
# ==========================================
class CarMakerXILBridge:
    def __init__(self):
        # We save the original dir so we can return if needed, but chdir to PROJECT_DIR is required for CarMaker
        os.chdir(PROJECT_DIR)
        self.config_file = os.path.join(PROJECT_DIR, "Config.xml")
        self._create_config_xml()

        print("\n[API] Booting CarMaker XIL Testbench...")
        factory = TestbenchFactory()
        self.testbench = factory.CreateVendorSpecificTestBench("IPG", "CarMaker", "14.1.1")
        self.ma_port = self.testbench.MAPortFactory.CreateMAPort("OptMAPort")

        config = self.ma_port.LoadConfiguration(self.config_file)
        self.ma_port.Configure(config, False)
        print("[API] Successfully connected to CarMaker Memory!\n")

    def _create_config_xml(self):
        xml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<PortConfigurations xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <MAPortConfig>
    <ProjectDir>{PROJECT_DIR}</ProjectDir>
    <Platform>office</Platform>
  </MAPortConfig>
</PortConfigurations>"""
        with open(self.config_file, "w") as f:
            f.write(xml_content)

    def run_lap(self):
        if self.ma_port.State != MAPortState.eSIMULATION_RUNNING:
            self.ma_port.StartSimulation(TESTRUN_FILE)
            self.ma_port.WaitForSimEnd(400.0)

    def close(self):
        if self.ma_port:
            if self.ma_port.State == MAPortState.eSIMULATION_RUNNING:
                self.ma_port.StopSimulation()
            self.ma_port.Dispose()

# ==========================================
# --- 6. The Objective Function ---
# ==========================================
def evaluate_lap_time(x, api, logger, vehicle_file):
    front_k = x[0]
    rear_k = x[1]
    
    print(f"--- Testing Setup | Front: {front_k:.1f} N/m | Rear: {rear_k:.1f} N/m ---")
    
    modify_vehicle_parameters(vehicle_file, {
        "SuspF.Spring": front_k,
        "SuspR.Spring": rear_k
    })
    
    api.run_lap() 
    
    log_file = get_latest_results_file()
    raw_time, cones, total_time = extract_lap_data(log_file)
    
    logger.log_run(round(front_k, 1), round(rear_k, 1), raw_time, cones, total_time)
    
    print(f"--> Result: {total_time:.3f} s (Raw: {raw_time}s | Cones: {cones})\n")
    return total_time

# ==========================================
# --- 7. Main Optimization Loop ---
# ==========================================
if __name__ == "__main__":
    VEHICLE_FILE, VEHICLE_NAME = select_vehicle()
    
    print("Starting 2D CarMaker XIL Optimization Pipeline...")
    
    api = CarMakerXILBridge()
    
    # Pass the script's original directory to the logger
    logger = CSVLogger(SCRIPT_DIR, VEHICLE_NAME)
    
    initial_guess = [20000.0, 20000.0] 
    bounds = ((20000.0, 80000.0), (20000.0, 80000.0))
    
    try:
        result = minimize(
            evaluate_lap_time, 
            initial_guess,
            args=(api, logger, VEHICLE_FILE), 
            method='Powell',
            bounds=bounds,
            options={'xtol': 500.0, 'disp': True} 
        )
        
        # ==========================================
        # NEW: Finalize the file with the absolute best setup
        # ==========================================
        best_front = result.x[0]
        best_rear = result.x[1]
        
        print("\n[INFO] Optimization finished. Locking in the fastest setup...")
        modify_vehicle_parameters(VEHICLE_FILE, {
            "SuspF.Spring": best_front,
            "SuspR.Spring": best_rear
        })
        
        print("\n=========================================")
        print("OPTIMIZATION COMPLETE!")
        print(f"Vehicle Tested: {VEHICLE_NAME}")
        print(f"Fastest Front Spring: {best_front:.1f} N/m")
        print(f"Fastest Rear Spring:  {best_rear:.1f} N/m")
        print(f"Best Sprint Lap Time: {result.fun:.3f} s")
        print("=========================================")
        
    finally:
        print("\n[API] Closing connection...")
        api.close()