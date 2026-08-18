from pkmn_redeem.classify import classify_verify_response, classify_redeem_response
from pkmn_redeem.models import CodeStatus


def test_verify_recaptcha_block():
    response = {"couponResults": None, "error": "recaptcha_validation_failure",
                "localizedError": "The server was not able to validate your reCAPTCHA submission."}
    status, detail = classify_verify_response(response, "ABC123")
    assert status == CodeStatus.CAPTCHA_BLOCKED
    assert "reCAPTCHA" in detail


def test_verify_recaptcha_block_with_explicit_null_localized_error_still_gets_string_detail():
    # Real payloads observed with localizedError present but null -- .get(key, default)
    # would return None here (the key EXISTS), not the default. Regression guard for that bug.
    response = {"couponResults": None, "error": "recaptcha_validation_failure", "localizedError": None}
    status, detail = classify_verify_response(response, "ABC123")
    assert status == CodeStatus.CAPTCHA_BLOCKED
    assert isinstance(detail, str) and detail  # must not be None


def test_verify_valid_code_returns_none_pending_redeem():
    response = {"couponResults": [{"couponCode": "ABC123", "validationStatus": "valid"}], "error": None}
    status, detail = classify_verify_response(response, "ABC123")
    assert status is None


def test_verify_already_redeemed_is_rejected():
    response = {"couponResults": [{"couponCode": "ABC123", "validationStatus": "already_redeemed",
                                    "localizedError": "This code has already been redeemed."}], "error": None}
    status, detail = classify_verify_response(response, "ABC123")
    assert status == CodeStatus.REJECTED
    assert detail == "This code has already been redeemed."


def test_verify_code_missing_from_response_is_error_fatal():
    response = {"couponResults": [{"couponCode": "OTHERCODE", "validationStatus": "valid"}], "error": None}
    status, detail = classify_verify_response(response, "ABC123")
    assert status == CodeStatus.ERROR_FATAL


def test_redeem_success():
    response = {"redeemCouponResults": [{"couponCode": "ABC123", "redemptionSuccessful": True}], "error": None}
    status, detail = classify_redeem_response(response, "ABC123")
    assert status == CodeStatus.SUCCESS


def test_redeem_recaptcha_block_is_indeterminate():
    response = {"redeemCouponResults": None, "error": "recaptcha_validation_failure",
                "localizedError": "The server was not able to validate your reCAPTCHA submission."}
    status, detail = classify_redeem_response(response, "ABC123")
    assert status == CodeStatus.INDETERMINATE


def test_redeem_recaptcha_block_with_explicit_null_localized_error_still_gets_string_detail():
    response = {"redeemCouponResults": None, "error": "recaptcha_validation_failure", "localizedError": None}
    status, detail = classify_redeem_response(response, "ABC123")
    assert status == CodeStatus.INDETERMINATE
    assert isinstance(detail, str) and detail


def test_redeem_code_missing_from_response_is_indeterminate():
    response = {"redeemCouponResults": [{"couponCode": "OTHERCODE", "redemptionSuccessful": True}], "error": None}
    status, detail = classify_redeem_response(response, "ABC123")
    assert status == CodeStatus.INDETERMINATE


def test_redeem_explicit_false_is_rejected():
    response = {"redeemCouponResults": [{"couponCode": "ABC123", "redemptionSuccessful": False,
                                           "localizedError": "Redemption failed."}], "error": None}
    status, detail = classify_redeem_response(response, "ABC123")
    assert status == CodeStatus.REJECTED
    assert detail == "Redemption failed."


def test_redeem_missing_redemption_successful_field_is_indeterminate():
    response = {"redeemCouponResults": [{"couponCode": "ABC123"}], "error": None}
    status, detail = classify_redeem_response(response, "ABC123")
    assert status == CodeStatus.INDETERMINATE


def test_redeem_null_redemption_successful_field_is_indeterminate():
    response = {"redeemCouponResults": [{"couponCode": "ABC123", "redemptionSuccessful": None}], "error": None}
    status, detail = classify_redeem_response(response, "ABC123")
    assert status == CodeStatus.INDETERMINATE
