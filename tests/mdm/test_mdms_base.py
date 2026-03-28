from apps.mdm.mdms import MDMAPIError


class TestMDMAPIError:
    def test_str_with_status_and_error_data(self):
        """MDMAPIError.__str__ includes status code and error data when both present."""
        err = MDMAPIError(status_code=400, error_data={"message": "Bad request"})
        result = str(err)
        assert "Status 400" in result
        assert "Bad request" in result

    def test_str_with_status_only(self):
        """MDMAPIError.__str__ returns only the status code when error_data is absent."""
        err = MDMAPIError(status_code=500)
        result = str(err)
        assert result == "Status 500"
        assert ":" not in result
