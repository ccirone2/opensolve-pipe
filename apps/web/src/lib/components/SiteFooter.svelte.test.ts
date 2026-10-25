import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import { LICENSE_URL, serverSourceHref, SOURCE_URL } from './links';
import SiteFooter from './SiteFooter.svelte';

describe('SiteFooter', () => {
	it('shows the copyright notice and the legal links', () => {
		render(SiteFooter);
		expect(screen.getByText('Copyright © 2026 Chris Cirone')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'License: AGPL-3.0-or-later' })).toHaveAttribute(
			'href',
			LICENSE_URL
		);
		expect(screen.getByRole('link', { name: 'Source code' })).toHaveAttribute('href', SOURCE_URL);
		expect(screen.getByRole('link', { name: 'Server source code' })).toHaveAttribute(
			'href',
			serverSourceHref()
		);
		expect(screen.getByRole('link', { name: 'Third-party licenses' })).toHaveAttribute(
			'href',
			'/third-party-licenses.txt'
		);
	});
});
