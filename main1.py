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


def normalize(value, min_value, max_value):
    return max(0, min(500, 500 * (value - min_value) / (max_value - min_value)))


def calculate_voc_index(gas_resistance):
    if gas_resistance < 10000:
        return 0
    elif gas_resistance < 50000:
        return normalize(gas_resistance, 10000, 50000) * (200 / 500)
    elif gas_resistance < 100000:
        return normalize(gas_resistance, 50000, 100000) + 200
    else:
        return 500

def calculate_temperature_index(temperature):
    if temperature < 18:
        return normalize(temperature, 0, 18)
    elif temperature > 25:
        return normalize(temperature, 25, 50)
    else:
        return 500


def calculate_humidity_index(humidity):
    if humidity < 40:
        return normalize(humidity, 0, 40)
    elif humidity > 70:
        return normalize(humidity, 70, 100)
    else:
        return 500


def calculate_iaq(temperature, humidity, gas_resistance):
    voc_index = calculate_voc_index(gas_resistance)
    temp_index = calculate_temperature_index(temperature)
    humidity_index = calculate_humidity_index(humidity)

    iaq = (0.5 * voc_index) + (0.25 * temp_index) + (0.25 * humidity_index)

    return iaq

def sensor_data():
    try:
        if sensor.get_sensor_data():
            output = f'BME680: Temp: {sensor.data.temperature:.1f} C, Humidity: {sensor.data.humidity:.1f} %, Pressure: {sensor.data.pressure:.1f} hPa,'
            if sensor.data.heat_stable:
                gas_resistance = sensor.data.gas_resistance / 1000

                iaq = (sensor.data.gas_resistance * sensor.data.temperature) / (sensor.data.humidity / 100)
                iaqn1 = (iaq - 75000) / (4375000 - 75000) * 500

                iaqn2 = calculate_iaq(sensor.data.temperature, sensor.data.humidity, sensor.data.gas_resistance)
                output += f' Gas: {gas_resistance:.3f} Ohms, iaq1: {iaqn1:.2f}, iaq2: {iaqn2:.2f},'
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
