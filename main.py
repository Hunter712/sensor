import bme680
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app)
sensor_task_running = False

try:
    sensor = bme680.BME680(bme680.I2C_ADDR_PRIMARY)
except (RuntimeError, IOError):
    sensor = bme680.BME680(bme680.I2C_ADDR_SECONDARY)

# These calibration data can safely be commented
# out, if desired.

print('Calibration data:')
for name in dir(sensor.calibration_data):

    if not name.startswith('_'):
        value = getattr(sensor.calibration_data, name)

        if isinstance(value, int):
            print(f'{name}: {value}')

# These oversampling settings can be tweaked to
# change the balance between accuracy and noise in
# the data.

sensor.set_humidity_oversample(bme680.OS_2X)
sensor.set_pressure_oversample(bme680.OS_4X)
sensor.set_temperature_oversample(bme680.OS_8X)
sensor.set_filter(bme680.FILTER_SIZE_3)
sensor.set_gas_status(bme680.ENABLE_GAS_MEAS)

for name in dir(sensor.data):
    value = getattr(sensor.data, name)

    if not name.startswith('_'):
        print(f'{name}: {value}')

sensor.set_gas_heater_temperature(320)
sensor.set_gas_heater_duration(150)
sensor.select_gas_heater_profile(0)


# Up to 10 heater profiles can be configured, each
# with their own temperature and duration.
# sensor.set_gas_heater_profile(200, 150, nb_profile=1)
# sensor.select_gas_heater_profile(1)
def sensor_data():
    try:
        if sensor.get_sensor_data():
            output = f'BME680 - Temp: {sensor.data.temperature:.1f} C, Humidity: {sensor.data.humidity:.1f} %, Pressure: {sensor.data.pressure:.1f} hPa,'
            if sensor.data.heat_stable:
                gas_resistance = sensor.data.gas_resistance / 1000
                iaq = (sensor.data.gas_resistance * sensor.data.temperature) / (sensor.data.humidity / 100)
                iaqn = (iaq - 75000) / (4375000 - 75000) * 500
                output += f' Gas: {gas_resistance:.3f} Ohms, iaq: {iaqn:.1f},'

                if iaqn <= 200:
                    output += ' air quality - bad,'
                elif iaqn <= 400:
                    output += ' air quality - normal,'
                elif iaqn > 400:
                    output += ' air quality - good,'

                if sensor.data.gas_resistance <= 10000:
                    output += ' gas resistance - dangerous,'
                elif sensor.data.gas_resistance <= 50000:
                    output += ' gas resistance - normal,'
                elif sensor.data.gas_resistance > 50000:
                    output += ' gas resistance - good,'

                if sensor.data.temperature < 18:
                    output += ' temperature - cold,'
                elif sensor.data.temperature > 18 and sensor.data.temperature < 26:
                    output += ' temperature - good,'
                elif sensor.data.temperature > 26:
                    output += ' temperature - hot,'

                if sensor.data.humidity < 30:
                    output += ' humidity - low,'
                elif sensor.data.humidity >= 30 and sensor.data.humidity <= 60:
                    output += ' humidity - good,'
                elif sensor.data.humidity > 60:
                    output += ' humidity - high,'

            else:
                output = None
        else:
            output = None
    except KeyboardInterrupt:
        output = None
    return output


@app.route('/')
def index():
    return render_template('index.html')


def send_sensor_data():
    while True:
        data = sensor_data()
        socketio.emit('sensor_update', data)
        socketio.sleep(10)


@socketio.on('connect')
def handle_connect():
    global sensor_task_running

    if not sensor_task_running:
        socketio.start_background_task(send_sensor_data)
        sensor_task_running = True

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
