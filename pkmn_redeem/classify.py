from typing import Optional

from .models import CodeStatus


def classify_verify_response(response_json: dict, code: str) -> tuple[Optional[CodeStatus], str]:
    if response_json.get("error") == "recaptcha_validation_failure":
        # .get(key) or default -- NOT .get(key, default) -- because real payloads carry
        # "localizedError": null explicitly; .get(key, default) only applies default when
        # the key is absent, not when it's present-and-None.
        return CodeStatus.CAPTCHA_BLOCKED, response_json.get("localizedError") or "reCAPTCHA validation failed"

    for entry in response_json.get("couponResults") or []:
        if entry.get("couponCode") == code:
            if entry.get("validationStatus") == "valid":
                return None, "verified, pending redeem"
            return CodeStatus.REJECTED, entry.get("localizedError") or f"validationStatus={entry.get('validationStatus')}"

    return CodeStatus.ERROR_FATAL, f"code {code} not present in verify response"


def classify_redeem_response(response_json: dict, code: str) -> tuple[CodeStatus, str]:
    if response_json.get("error") == "recaptcha_validation_failure":
        return CodeStatus.INDETERMINATE, response_json.get("localizedError") or "reCAPTCHA validation failed on redeem commit"

    for entry in response_json.get("redeemCouponResults") or []:
        if entry.get("couponCode") == code:
            successful = entry.get("redemptionSuccessful")
            if successful is True:
                return CodeStatus.SUCCESS, "redeemed"
            if successful is False:
                return CodeStatus.REJECTED, entry.get("localizedError") or "redemption not successful"
            return CodeStatus.INDETERMINATE, f"redemptionSuccessful missing/null for code {code}"

    return CodeStatus.INDETERMINATE, f"code {code} not present in redeem response"
