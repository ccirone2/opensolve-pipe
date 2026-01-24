"""Tests for solve API router."""

import pytest
from httpx import AsyncClient


class TestSolveProject:
    """Tests for POST /api/v1/solve endpoint."""

    @pytest.mark.anyio
    async def test_solve_empty_project(self, client: AsyncClient) -> None:
        """Should return error for empty project (no components)."""
        response = await client.post(
            "/api/v1/solve",
            json={
                "metadata": {"name": "Test Project"},
                "settings": {},
                "fluid": {"type": "water", "temperature": 68.0},
                "components": [],
                "pump_library": [],
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Empty project should fail with no components error
        assert data["converged"] is False
        assert "No components" in data["error"]
        assert len(data["warnings"]) > 0


class TestSolveSimple:
    """Tests for POST /api/v1/solve/simple endpoint."""

    @pytest.fixture
    def simple_pump_system(self) -> dict:
        """Basic pump-pipe system for testing."""
        return {
            "pump_curve": [
                {"flow": 0, "head": 100},
                {"flow": 50, "head": 95},
                {"flow": 100, "head": 85},
                {"flow": 150, "head": 70},
                {"flow": 200, "head": 50},
            ],
            "static_head_ft": 30.0,
            "pipe_length_ft": 500.0,
            "pipe_diameter_in": 4.0,
            "pipe_roughness_in": 0.0018,
            "fluid": {"type": "water", "temperature": 68.0},
            "total_k_factor": 10.0,
        }

    @pytest.mark.anyio
    async def test_solve_simple_converges(
        self, client: AsyncClient, simple_pump_system: dict
    ) -> None:
        """Should solve a basic pump-pipe system."""
        response = await client.post("/api/v1/solve/simple", json=simple_pump_system)

        assert response.status_code == 200
        data = response.json()

        assert data["converged"] is True
        assert data["error"] is None
        assert data["operating_flow_gpm"] is not None
        assert data["operating_head_ft"] is not None

    @pytest.mark.anyio
    async def test_solve_simple_returns_curves(
        self, client: AsyncClient, simple_pump_system: dict
    ) -> None:
        """Should return system and pump curves for visualization."""
        response = await client.post("/api/v1/solve/simple", json=simple_pump_system)

        assert response.status_code == 200
        data = response.json()

        assert len(data["system_curve"]) > 0
        assert len(data["pump_curve"]) > 0

        # Check curve point structure
        for point in data["system_curve"]:
            assert len(point) == 2  # (flow, head)
            assert isinstance(point[0], int | float)
            assert isinstance(point[1], int | float)

    @pytest.mark.anyio
    async def test_solve_simple_returns_hydraulics(
        self, client: AsyncClient, simple_pump_system: dict
    ) -> None:
        """Should return detailed hydraulic parameters."""
        response = await client.post("/api/v1/solve/simple", json=simple_pump_system)

        assert response.status_code == 200
        data = response.json()

        assert data["velocity_fps"] is not None
        assert data["reynolds_number"] is not None
        assert data["friction_factor"] is not None
        assert data["total_head_loss_ft"] is not None
        assert data["npsh_available_ft"] is not None

    @pytest.mark.anyio
    async def test_solve_simple_reasonable_operating_point(
        self, client: AsyncClient, simple_pump_system: dict
    ) -> None:
        """Operating point should be within reasonable bounds."""
        response = await client.post("/api/v1/solve/simple", json=simple_pump_system)

        assert response.status_code == 200
        data = response.json()

        # Flow should be positive and in a reasonable range
        assert 0 < data["operating_flow_gpm"] < 500

        # Head should be above static head
        assert data["operating_head_ft"] > simple_pump_system["static_head_ft"]

    @pytest.mark.anyio
    async def test_solve_simple_pump_cannot_overcome_head(
        self, client: AsyncClient
    ) -> None:
        """Should fail when pump can't overcome static head."""
        response = await client.post(
            "/api/v1/solve/simple",
            json={
                "pump_curve": [
                    {"flow": 0, "head": 50},
                    {"flow": 100, "head": 30},
                ],
                "static_head_ft": 100.0,  # Higher than pump shutoff
                "pipe_length_ft": 100.0,
                "pipe_diameter_in": 4.0,
                "pipe_roughness_in": 0.0018,
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["converged"] is False
        assert "cannot overcome" in data["error"].lower()

    @pytest.mark.anyio
    async def test_solve_simple_insufficient_pump_curve_points(
        self, client: AsyncClient
    ) -> None:
        """Should return 422 for pump curve with < 2 points."""
        response = await client.post(
            "/api/v1/solve/simple",
            json={
                "pump_curve": [{"flow": 0, "head": 100}],  # Only 1 point
                "static_head_ft": 30.0,
                "pipe_length_ft": 500.0,
                "pipe_diameter_in": 4.0,
                "pipe_roughness_in": 0.0018,
            },
        )

        assert response.status_code == 422

    @pytest.mark.anyio
    async def test_solve_simple_with_different_temperature(
        self, client: AsyncClient, simple_pump_system: dict
    ) -> None:
        """Should solve with water at different temperature."""
        simple_pump_system["fluid"]["temperature"] = 140.0  # Hot water
        response = await client.post("/api/v1/solve/simple", json=simple_pump_system)

        assert response.status_code == 200
        data = response.json()

        assert data["converged"] is True
        # Higher temperature = lower viscosity = slightly higher flow
        assert data["operating_flow_gpm"] is not None

    @pytest.mark.anyio
    async def test_solve_simple_with_celsius(
        self, client: AsyncClient, simple_pump_system: dict
    ) -> None:
        """Should accept temperature in Celsius."""
        simple_pump_system["fluid"]["temperature"] = 20.0
        simple_pump_system["temperature_unit"] = "C"

        response = await client.post("/api/v1/solve/simple", json=simple_pump_system)

        assert response.status_code == 200
        data = response.json()
        assert data["converged"] is True

    @pytest.mark.anyio
    async def test_solve_simple_with_diesel(self, client: AsyncClient) -> None:
        """Should solve with diesel fuel."""
        response = await client.post(
            "/api/v1/solve/simple",
            json={
                "pump_curve": [
                    {"flow": 0, "head": 100},
                    {"flow": 100, "head": 70},
                ],
                "static_head_ft": 20.0,
                "pipe_length_ft": 200.0,
                "pipe_diameter_in": 3.0,
                "pipe_roughness_in": 0.0018,
                "fluid": {"type": "diesel", "temperature": 68.0},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["converged"] is True

    @pytest.mark.anyio
    async def test_solve_simple_invalid_diameter(self, client: AsyncClient) -> None:
        """Should return 422 for invalid pipe diameter."""
        response = await client.post(
            "/api/v1/solve/simple",
            json={
                "pump_curve": [
                    {"flow": 0, "head": 100},
                    {"flow": 100, "head": 70},
                ],
                "static_head_ft": 20.0,
                "pipe_length_ft": 200.0,
                "pipe_diameter_in": -1.0,  # Invalid
                "pipe_roughness_in": 0.0018,
            },
        )

        assert response.status_code == 422


class TestHealthCheck:
    """Tests for health check endpoint."""

    @pytest.mark.anyio
    async def test_health_check(self, client: AsyncClient) -> None:
        """Health endpoint should return healthy."""
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestRootEndpoint:
    """Tests for root endpoint."""

    @pytest.mark.anyio
    async def test_root_endpoint(self, client: AsyncClient) -> None:
        """Root endpoint should return API info."""
        response = await client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "OpenSolve Pipe API"
        assert "version" in data
        assert "docs" in data
