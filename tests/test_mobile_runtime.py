from src.mobile_node import DeviceType, MobileNode, MobileTask, NPUChip


def test_mobile_task_requires_handler():
    node = MobileNode(DeviceType.PHONE, node_id="phone-a")
    node.start()
    result = node.process_task(MobileTask("task-1", "classification", "hello"))
    assert result["status"] == "UNSUPPORTED"
    assert node.completed_tasks == []


def test_mobile_registered_handler_completes_task():
    node = MobileNode(DeviceType.TABLET, node_id="tablet-a")
    node.register_handler("classification", lambda task: {"status": "COMPLETED", "label": "ok"})
    node.start()
    task = MobileTask("task-2", "classification", "hello")
    assert node.submit_task(task) is True
    result = node.process_next()
    assert result["status"] == "COMPLETED"
    assert result["label"] == "ok"
    assert len(node.completed_tasks) == 1


def test_mobile_status_identifies_measurement_boundary():
    node = MobileNode(DeviceType.PHONE, node_id="phone-a")
    status = node.get_status()
    assert status["claim"] == "OBSERVED_OR_OPERATOR_CONFIGURED_CAPABILITIES_ONLY"
    assert isinstance(node.capability.npu_chip, NPUChip)
