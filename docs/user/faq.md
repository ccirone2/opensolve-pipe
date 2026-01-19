# Frequently Asked Questions

## General Questions

### What is OpenSolve Pipe?

OpenSolve Pipe is a free, browser-based tool for steady-state hydraulic analysis of pressurized pipe systems. It calculates pressures, flows, and head losses in networks with pumps, pipes, and fittings.

### Do I need to create an account?

No. OpenSolve Pipe works entirely in your browser with no login required. Projects are stored in the URL, so you can save and share by copying the link.

### Is my data secure?

Your project data stays in your browser. Small projects are encoded in the URL and never sent to our servers for storage. Only when you click "Solve" is your data sent to our calculation server (and immediately discarded after solving).

### What browsers are supported?

OpenSolve Pipe works in all modern browsers:

- Chrome (recommended)
- Firefox
- Safari
- Edge

### Does it work on mobile?

Yes! The panel navigator is designed for mobile devices. You can create and solve projects on your phone or tablet.

## Technical Questions

### What calculation method does OpenSolve Pipe use?

We use the Darcy-Weisbach equation for friction losses with the Colebrook equation for friction factor. Minor losses are calculated using K-factors from Crane TP-410.

### How accurate are the results?

Results typically match EPANET and hand calculations within 1%. For critical applications, always verify results with independent methods.

### Why did my solution not converge?

Common causes:

1. **Impossible physics**: Check valve in wrong direction, pump running backward
2. **Disconnected network**: Make sure all components are connected
3. **Extreme conditions**: Very high velocities or pressure drops
4. **Missing pump curve**: Pump without curve data

### What's the maximum network size?

The URL-encoded approach works well for projects under 50 components. Larger projects may need server storage (coming in future versions).

### Can I analyze branching networks?

The MVP supports single-path systems (one main flow path). Branching and looped networks are planned for future releases.

## Calculation Questions

### How is NPSH calculated?

NPSH Available = Suction head + Atmospheric pressure - Vapor pressure - Suction losses

We assume standard atmospheric pressure (14.7 psi) unless specified otherwise.

### What K-factors does OpenSolve Pipe use?

K-factors are based on Crane TP-410, the standard reference for flow of fluids through valves and fittings.

### How are pump curves interpolated?

Pump curves use cubic spline interpolation between data points. We recommend entering at least 5 points for smooth results.

### What roughness values are used?

| Material | Roughness (in) |
|----------|---------------|
| New steel | 0.0018 |
| Commercial steel | 0.0018 |
| PVC/Plastic | 0.00006 |
| Copper | 0.00006 |
| Cast iron (new) | 0.010 |
| Cast iron (old) | 0.040 |
| Concrete | 0.012 |

## Troubleshooting

### The Solve button is disabled

The Solve button is disabled when:

- Project has no components
- A solve is already in progress

### Results show negative pressure

Negative gage pressure indicates vacuum conditions. This may indicate:

- Suction lift is too high
- Pipe velocities are excessive
- Cavitation risk

### Flow shows zero

If flow is zero:

- Check that pump has a curve assigned
- Verify static head isn't higher than pump shutoff head
- Ensure there's a flow path from source to sink

### Error: "Network request failed"

This usually means:

- You're offline
- The calculation server is temporarily unavailable
- Your network blocks the API

Try refreshing the page or checking your connection.

## Feature Requests

### How do I request a feature?

Open an issue on our [GitHub repository](https://github.com/ccirone2/opensolve-pipe/issues) with the "enhancement" label.

### Is OpenSolve Pipe open source?

Yes! The code is available on [GitHub](https://github.com/ccirone2/opensolve-pipe) under the MIT license.

## Getting Help

- **Documentation**: This site
- **GitHub Issues**: Bug reports and feature requests
- **Email**: (coming soon)
