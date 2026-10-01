from src.marketplace_video import handoff_event


def test_handoff_event_marks_order_and_buyer():
    event = handoff_event("order-1042", "buyer-22", "seller-7")
    assert event == {
        "order_id": "order-1042",
        "buyer_id": "buyer-22",
        "state": "handed_off",
        "account_id": "seller-7",
    }
