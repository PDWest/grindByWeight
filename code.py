import time
import board
import rotaryio
import digitalio

# 1. Bind the encoder to your confirmed pins
encoder = rotaryio.IncrementalEncoder(board.ENC_A, board.ENC_B)
last_position = 0

# 1b. Configure the rear Port B output pin (GPIO2) as a digital output.
#     It mirrors the encoder parity: '1' for odd positions, '0' for even.
portb = digitalio.DigitalInOut(board.PORTB_OUT)
portb.direction = digitalio.Direction.OUTPUT
portb.value = bool(last_position % 2)

# 2. Clear the screen text layers using terminal escape codes
print("\033[2J\033[H") 
print("==============================")
print("     M5 DIAL ENCODER SYSTEM!   ")
print("==============================")
print(f"Current Position: {last_position}")

# 3. Continuous Monitoring Loop
while True:
    current_position = encoder.position
    
    if current_position != last_position:
        last_position = current_position

        # Odd position -> Port B high ('1'), even position -> Port B low ('0').
        # Python's modulo is always non-negative, so this also works for
        # negative encoder positions.
        portb.value = bool(current_position % 2)

        # \033[2J\033[H clears the screen and moves the cursor to the top left
        print("\033[2J\033[H")
        print("==============================")
        print("     M5 DIAL ENCODER SYSTEM!  ")
        print("==============================")
        print(f"Current Position: {current_position}")
        print(f"Port B Output:    {int(portb.value)}")

    time.sleep(0.01)
    
#######################################
