# grindByWeight

Project goal
Build a simple inexpensive device that can be used with almost any coffee grinder to allow the user to grind by weight.

We use an M5StackDial is the main UI/Microcontroller with the idea that it will allow the user to set a desired weight and press 'start'.  This will engage an SSR to energize the grinder.  A load cell under the grinder catch cup will be read by the M5, the weight will be displayed, and when it reaches the desired threshold, the power to the grinder will be cut off.


