import sys
import os
import glob
import re
import time
import csv
from datetime import datetime
from scipy.optimize import minimize

# ==========================================
# --- 1. Hooking into the ASAM XIL API ---
# ==========================================
CARMAKER_PYTHON_DIR = r"C:\IPG\carmaker\win64-14.1.1\Python\python3.12"
sys.path.append(CARMAKER_PYTHON_DIR)

from ASAM.XIL.Implementation.Testbench import TestbenchFactory
from ASAM.XIL.Interfaces.Testbench.MAPort.Enum.MAPortState import MAPortState

PROJECT_DIR  = r"C:\CM_Projects\FS_LTS_2025_v1"
VEHICLE_FILE = r"C:\CM_Projects\FS_LTS_2025_v1\Data\Vehicle\Baseline_Vehicles\Aero_4EM.car"
TESTRUN_FILE = "FS_Sprint_2025" 

# ==========================================
# --- 2. CSV Logging Class ---
# ==========================================
class CSVLogger:
    def __init__(self, project_dir):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = os.path.join(project_dir, f"Optimization_2D_{timestamp}.csv")
        
        # Headers upgraded for 2 variables
        self.headers = ["Front Spring [N/m]", "Rear Spring [N/m]", "Raw Lap Time [s]", "Cones Hit", "Total Time [s]"]
        with open(self.filename, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(self.headers)
        print(f"[LOG] Results will be saved to: {self.filename}")

    def log_run(self, front_k, rear_k, raw_time, cones, total_time):
        with open(self.filename, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([front_k, rear_k, raw_time, cones, total_time])

# ==========================================
# --- 3. Helper Functions ---
# ==========================================
def modify_vehicle_parameters(file_path, params_dict):
    """Upgraded to handle a dictionary of multiple parameters at once."""
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
# --- 4. The XIL API Bridge ---
# ==========================================
class CarMakerXILBridge:
    def __init__(self):
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
# --- 5. The Objective Function ---
# ==========================================
def evaluate_lap_time(x, api, logger):
    """x is now an array: x[0] = Front Spring, x[1] = Rear Spring"""
    front_k = x[0]
    rear_k = x[1]
    
    print(f"--- Testing Setup | Front: {front_k:.1f} N/m | Rear: {rear_k:.1f} N/m ---")
    
    # Update both parameters simultaneously
    modify_vehicle_parameters(VEHICLE_FILE, {
        "SuspF.Spring": front_k,
        "SuspR.Spring": rear_k
    })
    
    api.run_lap() 
    
    log_file = get_latest_results_file()
    raw_time, cones, total_time = extract_lap_data(log_file)
    
    # LOG TO CSV
    logger.log_run(round(front_k, 1), round(rear_k, 1), raw_time, cones, total_time)
    
    print(f"--> Result: {total_time:.3f} s (Raw: {raw_time}s | Cones: {cones})\n")
    return total_time

# ==========================================
# --- 6. Main Optimization Loop ---
# ==========================================
if __name__ == "__main__":
    print("Starting 2D CarMaker XIL Optimization Pipeline...")
    
    api = CarMakerXILBridge()
    logger = CSVLogger(PROJECT_DIR)
    
    # 1. Initial Guess (Where the optimizer starts looking)
    initial_guess = [40000.0, 40000.0] 
    
    # 2. Safety Bounds ((Front Min, Front Max), (Rear Min, Rear Max))
    bounds = ((20000.0, 80000.0), (20000.0, 80000.0))
    
    try:
        # Run the multi-variable optimizer using the Powell method
        result = minimize(
            evaluate_lap_time, 
            initial_guess,
            args=(api, logger), 
            method='Powell',
            bounds=bounds,
            options={'xtol': 500.0, 'disp': True} 
        )
        
        print("\n=========================================")
        print("OPTIMIZATION COMPLETE!")
        print(f"Fastest Front Spring: {result.x[0]:.1f} N/m")
        print(f"Fastest Rear Spring:  {result.x[1]:.1f} N/m")
        print(f"Best Sprint Lap Time: {result.fun:.3f} s")
        print("=========================================")
        
    finally:
        print("\n[API] Closing connection...")
        api.close()