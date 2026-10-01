"""Render real dashboard failure states without its refresh loop."""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('state', ['empty', 'zero', 'failures'])
def test_failure_states(state, tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_ROOT', str(tmp_path))
    if state != 'empty':
        (tmp_path / 'quality').mkdir()
        pd.DataFrame([{'batch_file': 'orders.csv', 'rows_in': 50,
                       'rows_out': 47 if state == 'failures' else 50,
                       'fail_order_id': 0, 'fail_distance_km': 3 if state == 'failures' else 0}]
                     ).to_csv(tmp_path / 'quality/batch_quality.csv', index=False)
    source = ('from unittest.mock import patch\nfrom pipeline.dashboard import app\n'
              'with patch.object(app.st.sidebar, "checkbox", return_value=False):\n    app.main()')
    rendered = AppTest.from_string(source).run(timeout=10)
    assert not rendered.exception
    heading = rendered.subheader[-1].value
    messages = [item.value for item in rendered.info]
    if state == 'failures':
        assert heading == 'distance_km causes the most preprocess failures'
        assert len(rendered.get('vega_lite_chart')) == 1
        assert not any('No field failures' in message for message in messages)
    else:
        assert heading == 'No field failures recorded'
        assert len(rendered.get('vega_lite_chart')) == 0
        if state == 'zero':
            assert not any('waiting for preprocess' in message for message in messages)
        assert messages[-1] == (
            'No preprocessing results yet — waiting for preprocess.' if state == 'empty'
            else 'Preprocessing completed with no field failures recorded.')



def test_enabled_refresh_finishes_and_checkbox_can_disable_it(tmp_path, monkeypatch):
    """A real auto-enabled script must finish well inside the stop grace period.

    The previous sleep(15) loop times out here. Actual browser timer/shutdown
    verification remains a separate Docker browser gate.
    """
    monkeypatch.setenv('DATA_ROOT', str(tmp_path))
    rendered = AppTest.from_string('from pipeline.dashboard.app import main; main()')
    rendered.run(timeout=5)
    assert not rendered.exception
    assert rendered.checkbox[0].value is True
    assert rendered.subheader[-1].value == 'No field failures recorded'
    rendered.checkbox[0].uncheck().run(timeout=5)
    assert not rendered.exception
    assert rendered.checkbox[0].value is False
    rendered.checkbox[0].check().run(timeout=5)
    assert not rendered.exception
    assert rendered.checkbox[0].value is True
