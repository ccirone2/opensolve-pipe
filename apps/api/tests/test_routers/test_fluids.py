"""Tests for fluids API router."""

import pytest
from httpx import AsyncClient


class TestListFluids:
    """Tests for GET /api/v1/fluids endpoint."""

    @pytest.mark.anyio
    async def test_list_fluids_returns_list(self, client: AsyncClient) -> None:
        """Should return a list of available fluids."""
        response = await client.get("/api/v1/fluids")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    @pytest.mark.anyio
    async def test_list_fluids_contains_water(self, client: AsyncClient) -> None:
        """Should include water in the list."""
        response = await client.get("/api/v1/fluids")

        assert response.status_code == 200
        data = response.json()

        water = next((f for f in data if f["id"] == "water"), None)
        assert water is not None
        assert water["name"] == "Water"
        assert water["type"] == "temperature_dependent"

    @pytest.mark.anyio
    async def test_list_fluids_structure(self, client: AsyncClient) -> None:
        """Each fluid should have required fields."""
        response = await client.get("/api/v1/fluids")

        assert response.status_code == 200
        data = response.json()

        for fluid in data:
            assert "id" in fluid
            assert "name" in fluid
            assert "type" in fluid


class TestListFluidTypes:
    """Tests for GET /api/v1/fluids/types endpoint."""

    @pytest.mark.anyio
    async def test_list_fluid_types(self, client: AsyncClient) -> None:
        """Should return all fluid type enum values."""
        response = await client.get("/api/v1/fluids/types")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Check for expected types
        values = [t["value"] for t in data]
        assert "water" in values
        assert "diesel" in values
        assert "custom" in values

    @pytest.mark.anyio
    async def test_fluid_types_structure(self, client: AsyncClient) -> None:
        """Each type should have value and name."""
        response = await client.get("/api/v1/fluids/types")

        assert response.status_code == 200
        data = response.json()

        for fluid_type in data:
            assert "value" in fluid_type
            assert "name" in fluid_type


class TestGetFluidProperties:
    """Tests for GET /api/v1/fluids/{fluid_id}/properties endpoint."""

    @pytest.mark.anyio
    async def test_water_properties_fahrenheit(self, client: AsyncClient) -> None:
        """Should return water properties at 68°F."""
        response = await client.get(
            "/api/v1/fluids/water/properties",
            params={"temperature": 68.0, "temperature_unit": "F"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "density" in data
        assert "kinematic_viscosity" in data
        assert "dynamic_viscosity" in data
        assert "vapor_pressure" in data
        assert "specific_gravity" in data

        # Water at 68°F (20°C) should have density ~998 kg/m³
        assert 995 < data["density"] < 1000

    @pytest.mark.anyio
    async def test_water_properties_celsius(self, client: AsyncClient) -> None:
        """Should return water properties at 20°C."""
        response = await client.get(
            "/api/v1/fluids/water/properties",
            params={"temperature": 20.0, "temperature_unit": "C"},
        )

        assert response.status_code == 200
        data = response.json()

        # Same as 68°F
        assert 995 < data["density"] < 1000

    @pytest.mark.anyio
    async def test_diesel_properties(self, client: AsyncClient) -> None:
        """Should return diesel fuel properties."""
        response = await client.get("/api/v1/fluids/diesel/properties")

        assert response.status_code == 200
        data = response.json()

        # Diesel has fixed properties
        assert 800 < data["density"] < 900  # ~850 kg/m³

    @pytest.mark.anyio
    async def test_invalid_fluid_returns_404(self, client: AsyncClient) -> None:
        """Should return 404 for unknown fluid type."""
        response = await client.get("/api/v1/fluids/invalid_fluid/properties")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "fluid_not_found"

    @pytest.mark.anyio
    async def test_temperature_out_of_range(self, client: AsyncClient) -> None:
        """Should return 400 for temperature outside valid range."""
        # Water properties are only valid 0-100°C
        response = await client.get(
            "/api/v1/fluids/water/properties",
            params={"temperature": 500.0, "temperature_unit": "F"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "temperature_out_of_range"

    @pytest.mark.anyio
    async def test_glycol_not_implemented(self, client: AsyncClient) -> None:
        """Should return 501 for glycol fluids (not yet implemented)."""
        response = await client.get(
            "/api/v1/fluids/ethylene_glycol/properties",
            params={"concentration": 30},
        )

        assert response.status_code == 501
        data = response.json()
        assert data["detail"]["error"] == "not_implemented"

    @pytest.mark.anyio
    async def test_invalid_temperature_unit(self, client: AsyncClient) -> None:
        """Should return 422 for invalid temperature unit."""
        response = await client.get(
            "/api/v1/fluids/water/properties",
            params={"temperature_unit": "X"},
        )

        assert response.status_code == 422  # Validation error


class TestCalculateFluidProperties:
    """Tests for POST /api/v1/fluids/properties endpoint."""

    @pytest.mark.anyio
    async def test_calculate_water_properties(self, client: AsyncClient) -> None:
        """Should calculate water properties from definition."""
        response = await client.post(
            "/api/v1/fluids/properties",
            json={"type": "water", "temperature": 68.0},
            params={"temperature_unit": "F"},
        )

        assert response.status_code == 200
        data = response.json()
        assert 995 < data["density"] < 1000

    @pytest.mark.anyio
    async def test_calculate_custom_fluid_properties(self, client: AsyncClient) -> None:
        """Should return custom fluid properties as-is."""
        response = await client.post(
            "/api/v1/fluids/properties",
            json={
                "type": "custom",
                "temperature": 68.0,
                "custom_density": 850.0,
                "custom_kinematic_viscosity": 3e-6,
                "custom_vapor_pressure": 1000.0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["density"] == 850.0
        assert data["kinematic_viscosity"] == 3e-6
        assert data["vapor_pressure"] == 1000.0

    @pytest.mark.anyio
    async def test_custom_fluid_missing_properties(self, client: AsyncClient) -> None:
        """Should return 422 for custom fluid without required properties."""
        response = await client.post(
            "/api/v1/fluids/properties",
            json={"type": "custom", "temperature": 68.0},
        )

        assert response.status_code == 422  # Validation error
