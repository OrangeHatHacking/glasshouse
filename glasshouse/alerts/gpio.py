"""
GPIO alert module for LED patterns and the buzzer.

LED (GPIO 17): breathing during idle scan, flash patterns on detection.
Buzzer (GPIO 18): PWM stub. Wire up the buzzer and uncomment BUZZER_ENABLED.

Designed to degrade gracefully: if RPi.GPIO is not available (dev machine),
all functions become no-ops and log at DEBUG level.
"""

import asyncio
import logging

log = logging.getLogger(__name__)

LED_PIN = 17
BUZZER_PIN = 18
BUZZER_ENABLED = False  # Set True when buzzer is physically connected
_led_enabled = True

_gpio_available = False
_breathing_task: asyncio.Task | None = None
_gpio = None
_pwm_led = None
_pwm_buzzer = None


def set_led_enabled(enabled: bool) -> None:
    global _led_enabled
    _led_enabled = enabled
    if not enabled:
        _led_off()


def _setup_gpio() -> bool:
    global _gpio_available, _gpio, _pwm_led, _pwm_buzzer
    try:
        from RPi import GPIO

        _gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(LED_PIN, GPIO.OUT)
        _pwm_led = GPIO.PWM(LED_PIN, 1000)  # 1kHz PWM for LED
        _pwm_led.start(0)

        if BUZZER_ENABLED:
            GPIO.setup(BUZZER_PIN, GPIO.OUT)
            _pwm_buzzer = GPIO.PWM(BUZZER_PIN, 2000)
            _pwm_buzzer.start(0)

        _gpio_available = True
        log.info(
            "GPIO initialised (LED=GPIO%d, buzzer stub=GPIO%d)", LED_PIN, BUZZER_PIN
        )
        return True
    except ImportError:
        log.debug("RPi.GPIO not available - GPIO alerts disabled (dev mode)")
        return False
    except Exception as e:
        log.warning("GPIO setup failed: %s", e)
        return False


def init() -> None:
    _setup_gpio()


def cleanup() -> None:
    if _gpio_available and _gpio:
        if _pwm_led:
            _pwm_led.stop()
        if _pwm_buzzer:
            _pwm_buzzer.stop()
        _gpio.cleanup()


# ---------------------------------------------------------------------------
# LED helpers
# ---------------------------------------------------------------------------


def _led_duty(duty: float) -> None:
    """Set LED PWM duty cycle (0-100)."""
    if _led_enabled and _gpio_available and _pwm_led:
        _pwm_led.ChangeDutyCycle(max(0.0, min(100.0, duty)))


def _led_off() -> None:
    _led_duty(0)


def _led_full() -> None:
    _led_duty(100)


# ---------------------------------------------------------------------------
# Buzzer helpers. No-op until BUZZER_ENABLED = True.
# ---------------------------------------------------------------------------


def _beep(freq: int = 2000, duration: float = 0.1) -> None:
    if not BUZZER_ENABLED or not _gpio_available or not _pwm_buzzer:
        return
    _pwm_buzzer.ChangeFrequency(freq)
    _pwm_buzzer.ChangeDutyCycle(50)
    asyncio.get_event_loop().call_later(
        duration, lambda: _pwm_buzzer.ChangeDutyCycle(0)
    )


# ---------------------------------------------------------------------------
# Async alert patterns
# ---------------------------------------------------------------------------


async def breathing_loop(stop_event: asyncio.Event) -> None:
    """
    Soft breathing fade during idle scan.
    PWM duty 0 → 80 → 0 over ~4 seconds.
    Runs until stop_event is set.
    """
    if not _gpio_available:
        log.debug("breathing_loop: GPIO not available, no-op")
        while not stop_event.is_set():
            await asyncio.sleep(1)
        return

    step = 2
    duty = 0
    direction = step

    while not stop_event.is_set():
        _led_duty(duty)
        duty += direction
        if duty >= 80:
            direction = -step
        elif duty <= 0:
            direction = step
        await asyncio.sleep(0.05)

    _led_off()


async def flash_new_detection() -> None:
    """3 rapid flashes for a new detection."""
    if not _gpio_available:
        log.debug("flash_new_detection: GPIO not available")
        return
    for _ in range(3):
        _led_full()
        _beep(freq=2500, duration=0.1)
        await asyncio.sleep(0.1)
        _led_off()
        await asyncio.sleep(0.1)


async def flash_redetection() -> None:
    """2 flashes for a re-detection."""
    if not _gpio_available:
        log.debug("flash_redetection: GPIO not available")
        return
    for _ in range(2):
        _led_full()
        _beep(freq=2000, duration=0.08)
        await asyncio.sleep(0.08)
        _led_off()
        await asyncio.sleep(0.1)


async def flash_boot_ready() -> None:
    """Slow single blink on boot complete."""
    if not _gpio_available or not _led_enabled:
        return
    _led_full()
    await asyncio.sleep(0.5)
    _led_off()
    await asyncio.sleep(0.3)
    _led_full()
    await asyncio.sleep(0.5)
    _led_off()


async def flash_error() -> None:
    """Fast strobe on unrecoverable error."""
    if not _gpio_available:
        return
    for _ in range(10):
        _led_full()
        await asyncio.sleep(0.05)
        _led_off()
        await asyncio.sleep(0.05)


async def on_detection(event: dict) -> None:
    """
    Detection callback registered with the scanner.
    Routes to the appropriate flash pattern.
    """
    if event.get("redetection"):
        await flash_redetection()
    else:
        await flash_new_detection()
