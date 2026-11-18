/**
 * A case's box beside its name, as one unit (docs/proposals/pumps-nits.md §11.4, leftover L12;
 * ui-guide, "A case is its number"): one flex row, the box in a `shrink-0` span (`w-10` in the
 * reserved column), a space, then the name in a `min-w-0` span, so the box sits beside the name's
 * first line and every line of the name starts at one edge; the words heard "Case 2: Winter", the
 * Base box drawn and hidden from screen readers.
 */
import { render } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { besideCaseTag, designators, shownCaseTag, spokenWords } from '$lib/testing/helpers';
import CaseNamed from './CaseNamed.svelte';

afterEach(() => {
	document.body.innerHTML = '';
});

/** The unit drawn: its root, the box's span and the name's span. */
function unit() {
	const root = document.body.querySelector<HTMLElement>('[data-case-named]');
	expect(root, 'a [data-case-named] element').not.toBeNull();
	expect(root!.children).toHaveLength(2);
	const [box, name] = [...root!.children] as [HTMLElement, HTMLElement];
	return { root: root!, box, name };
}

describe('CaseNamed', () => {
	it('draws the box in a shrink-0 span, a space, then the name in a min-w-0 span, in one inline flex row on the words’ baseline; heard "Case 2: Winter"', () => {
		render(CaseNamed, { tag: 2, name: 'Winter' });
		const { root, box, name } = unit();
		expect(root).toHaveClass('inline-flex', 'max-w-full', 'items-baseline', 'gap-1');
		expect(root).toHaveClass('align-baseline');
		expect(box).toHaveClass('shrink-0');
		expect(box).not.toHaveClass('w-10');
		expect(box.firstElementChild).toHaveAttribute('data-case-tag');
		expect(shownCaseTag(box)).toBe('2');
		expect(name).toHaveClass('min-w-0', 'sm:wrap-break-word');
		expect(name.textContent).toBe('Winter');
		// The space between them: a text node, so the words heard keep it where no layout adds one.
		expect(box.nextSibling?.nodeType).toBe(Node.TEXT_NODE);
		expect(box.nextSibling?.textContent).toBe(' ');
		expect(spokenWords(root)).toBe('Case 2: Winter');
		expect(besideCaseTag(root)).toBe('Winter');
		expect(designators(root)).toEqual([]);
	});

	it('is a line of its own in block form, and keeps the reserved 2.5 rem column for the box in column form', () => {
		const block = render(CaseNamed, { tag: 3, name: 'Delivery tank 5 m higher', form: 'block' });
		let parts = unit();
		expect(parts.root).toHaveClass('flex', 'items-baseline', 'gap-1');
		expect(parts.root).not.toHaveClass('inline-flex');
		expect(parts.box).toHaveClass('shrink-0');
		expect(parts.box).not.toHaveClass('w-10');
		block.unmount();
		render(CaseNamed, { tag: 3, name: 'Delivery tank 5 m higher', form: 'column' });
		parts = unit();
		expect(parts.root).toHaveClass('flex', 'items-baseline');
		expect(parts.box).toHaveClass('w-10', 'shrink-0');
		expect(spokenWords(parts.root)).toBe('Case 3: Delivery tank 5 m higher');
	});

	it('draws the Base box too, hidden wholly from screen readers, which hear the name alone', () => {
		render(CaseNamed, { tag: 'Base', name: 'Base case' });
		const { root, box } = unit();
		const tag = box.firstElementChild!;
		expect(tag).toHaveAttribute('data-case-tag');
		expect(tag).toHaveAttribute('aria-hidden', 'true');
		expect(tag.textContent).toBe('Base');
		expect(spokenWords(root)).toBe('Base case');
	});

	it('draws its children in the name’s span, words after the name included, and takes the name’s classes given', () => {
		const children = createRawSnippet(() => ({ render: () => '<span>Winter (shown)</span>' }));
		render(CaseNamed, { tag: 2, children, nameClass: 'font-medium', class: 'text-xs' });
		const { root, name } = unit();
		expect(root).toHaveClass('text-xs');
		expect(name).toHaveClass('min-w-0', 'font-medium');
		expect(name).not.toHaveClass('sm:wrap-break-word');
		expect(name.textContent).toBe('Winter (shown)');
		expect(spokenWords(root)).toBe('Case 2: Winter (shown)');
	});
});
