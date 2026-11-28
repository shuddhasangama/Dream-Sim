"""Height in both units (client answer 6, 2026-11-27).

Stored once, as whole centimetres (stats_json.height_cm). Entered and shown in cm
and feet/inches. Feet/inches are converted to cm (round to the nearest cm) and then
checked against the same cm range, so validation is identical in both units; the
feet/inches range shown to people is derived from that cm range. The JavaScript copy
is mobile/src/heightUnits.js (same numbers, tested against each other).
"""
from __future__ import annotations

CM_PER_INCH = 2.54
MIN_CM, MAX_CM = 140, 210


def ft_in_to_cm(feet, inches=0):
    return int(round((int(feet) * 12 + int(inches)) * CM_PER_INCH))


def cm_to_ft_in(cm):
    total = int(round(int(cm) / CM_PER_INCH))
    return total // 12, total % 12


def ft_in_label(cm):
    feet, inches = cm_to_ft_in(cm)
    return f"{feet}′ {inches}″"


def label(cm):
    """'170 cm (5′ 7″)', or '' when there is no height."""
    if cm in (None, ''):
        return ''
    try:
        value = int(cm)
    except (TypeError, ValueError):
        return ''
    return f"{value} cm ({ft_in_label(value)})"


def ft_in_range(low=MIN_CM, high=MAX_CM):
    """The feet/inches values whose cm conversion lands inside [low, high]."""
    inches = [n for n in range(36, 100) if low <= int(round(n * CM_PER_INCH)) <= high]
    return (inches[0] // 12, inches[0] % 12), (inches[-1] // 12, inches[-1] % 12)


def range_text(low=MIN_CM, high=MAX_CM):
    (f1, i1), (f2, i2) = ft_in_range(low, high)
    return f"{low}–{high} cm ({f1}′ {i1}″–{f2}′ {i2}″)"


def from_form(form, low=MIN_CM, high=MAX_CM):
    """(cm | None, error | None) from a form with height_cm and/or height_ft + height_in.
    cm wins when both are given, unless cm still equals height_cm_was (the value the
    page was rendered with: a no-JavaScript page cannot keep the boxes in step), in
    which case the feet/inches the member changed win. Blank everything = no height."""
    cm_raw = str(form.get('height_cm') or '').strip()
    ft_raw = str(form.get('height_ft') or '').strip()
    in_raw = str(form.get('height_in') or '').strip()
    was = str(form.get('height_cm_was') or '').strip()
    if cm_raw and was and cm_raw == was and (ft_raw or in_raw):
        try:
            # Only a CHANGED feet/inches pair wins: 171 cm displays as 5′ 7″ (= 170 cm),
            # and an untouched form must keep 171.
            if (int(ft_raw or 0), int(in_raw or 0)) != cm_to_ft_in(int(round(float(was)))):
                cm_raw = ''
        except ValueError:
            cm_raw = ''
    if cm_raw:
        try:
            value = int(round(float(cm_raw)))
        except ValueError:
            return None, 'Height should be a number of centimetres, or feet and inches.'
    elif ft_raw or in_raw:
        try:
            feet, inches = int(ft_raw or 0), int(in_raw or 0)
        except ValueError:
            return None, 'Height in feet and inches should be whole numbers.'
        if not 0 <= inches <= 11 or feet < 0:
            return None, 'Inches should be from 0 to 11.'
        value = ft_in_to_cm(feet, inches)
    else:
        return None, None
    if not low <= value <= high:
        return None, f'Height should be between {range_text(low, high)}.'
    return value, None
