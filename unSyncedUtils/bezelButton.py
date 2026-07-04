import board
import keypad
import microcontroller

# The dial bezel button is connected to GPIO 42
# Set value_when_pressed to False because the button grounds when pressed
bezel_button = keypad.Keys(
    (microcontroller.pin.GPIO42,), 
    value_when_pressed=False, 
    pull=True
)

while True:
    event = bezel_button.events.get()
    if event:
        if event.pressed:
            print("Bezel button clicked!")
        elif event.released:
            print("Bezel button released!")
