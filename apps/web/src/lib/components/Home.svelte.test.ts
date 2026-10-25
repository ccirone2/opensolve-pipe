import { render, screen, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import { decodeProject, fragmentOf } from '$lib/utils/encoding';
import { EXAMPLES } from '$lib/utils/examples';
import Home from './Home.svelte';
import { serverSourceHref, SOURCE_URL } from './links';

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
		// What the server receives, and where: request bodies (never logged), not addresses.
		const sent = screen.getByText(/^Solving sends the project to the calculation server/);
		expect(sent).toHaveTextContent(/and so does showing a pump's system curve/);
		expect(sent).toHaveTextContent(
			/send the fluid \(its type, temperature and concentration\) the same way/
		);
		expect(sent).toHaveTextContent(
			/travels in the body of each request, never in the address it is sent to\. The server's log keeps neither project data nor your IP address: for each request, only its method, path, HTTP version and status, and for a request the server fails on, the kind of failure\./
		);
		expect(
			screen.getByText(
				/OpenSolve Pipe is an engineering aid\. Its results support, but do not replace, the judgment\s+of a qualified engineer, and are provided without warranty\./
			)
		).toBeInTheDocument();
		expect(screen.getByText(/AGPL-3\.0-or-later/)).toHaveTextContent(
			/^Copyright © 2026 Chris Cirone\. OpenSolve Pipe is free software/
		);
		expect(screen.getByRole('link', { name: 'Source code' })).toHaveAttribute('href', SOURCE_URL);
		expect(screen.getByRole('link', { name: "calculation server's source code" })).toHaveAttribute(
			'href',
			serverSourceHref()
		);
		expect(screen.getByRole('link', { name: 'third-party licenses' })).toHaveAttribute(
			'href',
			'/third-party-licenses.txt'
		);
	});
});
