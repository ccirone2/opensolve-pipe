import { render, screen, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import { decodeProject, fragmentOf } from '$lib/utils/encoding';
import { EXAMPLES } from '$lib/utils/examples';
import Home from './Home.svelte';

describe('Home', () => {
	it('shows the product name', () => {
		render(Home);
		expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('OpenSolve Pipe');
	});

	it('starts a new project at /p', () => {
		render(Home);
		expect(screen.getByRole('link', { name: 'New project' })).toHaveAttribute('href', '/p');
	});

	it('links to each example, with the project in the fragment', () => {
		render(Home);
		const list = within(screen.getByRole('region', { name: 'Examples' }));
		for (const example of EXAMPLES) {
			const link = list.getByRole('link', { name: new RegExp(example.title) });
			const href = link.getAttribute('href') ?? '';
			expect(href).toMatch(/^\/p#[A-Za-z0-9_-]+$/);
			expect(decodeProject(fragmentOf(href))).toEqual(example.create());
		}
	});

	it('states the privacy model, the disclaimer and the license', () => {
		render(Home);
		expect(screen.getByText(/never stored on a server/)).toBeInTheDocument();
		expect(
			screen.getByText(
				/OpenSolve Pipe is an engineering aid\. Its results support, but do not replace, the judgment\s+of a qualified engineer, and are provided without warranty\./
			)
		).toBeInTheDocument();
		expect(screen.getByText(/AGPL-3\.0-or-later/)).toBeInTheDocument();
	});
});
