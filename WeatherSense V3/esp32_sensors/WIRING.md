# WeatherSense – ESP32 Wiring

## Wiring Diagram (ASCII)

```
                    ESP32 DEVKIT
         ┌─────────────────────────────────┐
         │                                 │
   3V3 ──┤ 3V3                          GND ├── GND
         │                                 │
         │  GPIO4 ──────────────── DHT Data │
         │  (pull-up 4.7kΩ to 3V3)         │
         │                                 │
         │  GPIO21 (SDA) ──── BMP280 SDA   │
         │  GPIO22 (SCL) ──── BMP280 SCL   │
         │  3V3 ───────────── BMP280 VCC   │
         │  GND ───────────── BMP280 GND   │
         │                                 │
         │  GPIO34 (VP) ───── Rain A0      │
         │  GND ───────────── Rain GND     │
         │  3V3 ───────────── Rain VCC     │
         │                                 │
         └─────────────────────────────────┘
```

---

## Sensor Wiring

### DHT11 / DHT22

| DHT Pin | ESP32 Pin | Notes                    |
|---------|-----------|--------------------------|
| VCC     | 3V3       | Power                    |
| DATA    | GPIO 4    | Add 4.7kΩ pull-up to 3V3 |
| GND     | GND       | Ground                   |

- Use **DHT22** for better accuracy (±0.5°C) and wider range (-40..80°C).
- Use **DHT11** for lower cost (0–50°C, ±2°C). Change `DHT_TYPE` in code.

### BMP280 (I2C)

| BMP280 Pin | ESP32 Pin |
|------------|-----------|
| VCC        | 3V3       |
| GND        | GND       |
| SDA        | GPIO 21   |
| SCL        | GPIO 22   |

- Some boards use **0x76**, others **0x77**. Code tries both.
- Use 4.7kΩ pull-ups on SDA and SCL if the module does not include them.

### Rain Sensor (analog)

| Rain Module | ESP32 Pin |
|-------------|-----------|
| VCC         | 3V3       |
| GND         | GND       |
| A0 (analog) | GPIO 34   |
| D0 (digital)| Not used  |

- Rain sensors usually output **low** when wet (rain) and **high** when dry.
- `RAIN_THRESHOLD` in code: raw ADC value below this = rain. Default 1500.
- Calibrate: read Serial output for `Rain ADC` when dry vs wet and adjust.

---

## Pin Summary

| Signal      | GPIO | ADC      |
|-------------|------|----------|
| DHT Data    | 4    | –        |
| BMP SDA     | 21   | –        |
| BMP SCL     | 22   | –        |
| Rain analog | 34   | ADC1_CH6 |
