# EM-GPS-logger

Python app to log data from sundry QAAFI equipment: 
- Vanilla garmin GPS (serial)
- Trimble AG-442 (tcpip)
- Dual EM38 (serial)

# Instructions

1. Turn on the router well before you need it. It takes ages to boot
without a DSL connection. It has two open wifi networks you can connect
your laptop to. You can talk to the rover by laptop -> WiFi  -> router
-> ethernet -> rover.

2. Connect the ethernet cable before turning on the rover station. Once
you have turned it on, pressing the "up" button displays the IP address
of the unit - it should be something like "10.0.0.3". If it's
"169.172...." then it means the rover hasn't found the dhcp server on
the router, and doesn't have an address.

3. You can examine / configure the rover via a web browser by going to that IP
address. The user/password for the web interface is admin/password. The
manual page is

https://precisionagsolutions.net/wp-content/uploads/2014/04/AG-542-Base-Station.pdf

4. Start the app. If you've been using it before, you may have to delete
the old .ini file where it was running. Ensure the IP address is
correct. The port number should be 5017 (defined in the "IO
Configuration" page in the admin page (3))

5. it should stop flashing red and you'll see the numbers stream past.
