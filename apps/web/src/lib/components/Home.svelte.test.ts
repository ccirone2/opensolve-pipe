import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import Home from './Home.svelte';

describe('Home', () => {
	it('shows the product name', () => {
		render(Home);
		expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('OpenSolve Pipe');
	});
});
