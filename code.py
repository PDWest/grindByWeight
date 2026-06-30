import time
import board
import rotaryio

# 1. Bind the encoder to your confirmed pins
encoder = rotaryio.IncrementalEncoder(board.ENC_A, board.ENC_B)
last_position = 0

# 2. Clear the screen text layers using terminal escape codes
print("\033[2J\033[H") 
print("==============================")
print("     M5 DIAL ENCODER SYSTEM   ")
print("==============================")
print(f"Current Position: {last_position}")

# 3. Continuous Monitoring Loop
while True:
    current_position = encoder.position
    
    if current_position != last_position:
        last_position = current_position
        
        # \033[2J\033[H clears the screen and moves the cursor to the top left
        print("\033[2J\033[H") 
        print("==============================")
        print("     M5 DIAL ENCODER SYSTEM   ")
        print("==============================")
        print(f"Current Position: {current_position}")
        
    time.sleep(0.01)
