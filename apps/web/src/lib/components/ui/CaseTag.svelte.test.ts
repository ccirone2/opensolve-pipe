/**
 * A case's number in a small box (owner, 2026-11-12, nit 5: "I don't like the use of special
 * characters to designate pumps and groups"; Q2 "By list place"; docs/proposals/pumps-nits.md item
 * 5, slice 5b): the box is seen and hidden from screen readers, which hear its number from
 * visually hidden words instead, "Case 3:" or "Cases 4, 5 and 6:"; the base case's "Base" is wholly
 * hidden, since the words beside it, "Base case", already say it. A box in a checkbox's label
 * keeps the label's visible words in the checkbox's name (WCAG 2.5.3, Label in Name).
 */
import { render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { designators, outOfSight } from '$lib/testing/helpers';
import CaseTag from './CaseTag.svelte';

afterEach(() => {
	document.body.innerHTML = '';
});

/** The tag drawn: its root, the box seen and the words heard. */
function parts(root: ParentNode = document.body) {
	const tag = root.querySelector<HTMLElement>('[data-case-tag]');
	expect(tag, 'a [data-case-tag] element').not.toBeNull();
	const box =
		tag!.getAttribute('aria-hidden') === 'true'
			? tag!
			: tag!.querySelector<HTMLElement>('[aria-hidden="true"]');
	// The words heard and not seen: each outermost element out of sight, outside the box.
	const hidden = [...tag!.querySelectorAll<HTMLElement>('*')].filter(
		(el) => !el.closest('[aria-hidden="true"]') && outOfSight(el) && el.textContent!.trim()
	);
	const heard = hidden.filter((el) => !hidden.some((other) => other !== el && other.contains(el)));
	return { tag: tag!, box, heard };
}

/**
 * A checkbox's label: the box, the tag (mounted at `anchor`), a space and the case's name, as the
 * lists have it (Svelte keeps one space between `<CaseTag />` and the name's span).
 */
function label(name: string) {
	const element = document.createElement('label');
	const checkbox = document.createElement('input');
	checkbox.type = 'checkbox';
	const anchor = document.createTextNode(' ');
	const words = document.createElement('span');
	words.textContent = name;
	element.append(checkbox, anchor, words);
	document.body.append(element);
	return { element, anchor, words };
}

describe('CaseTag', () => {
	it('shows a case’s number in a box hidden from screen readers, which hear "Case 3:"', () => {
		render(CaseTag, { tag: 3 });
		const { tag, box, heard } = parts();
		// Its number seen, in sight; the box itself aria-hidden, the tag not.
		expect(tag).not.toHaveAttribute('aria-hidden');
		expect(box).not.toBeNull();
		expect(box!.textContent!.trim()).toBe('3');
		expect(outOfSight(box!)).toBe(false);
		// The words heard: visually hidden, outside the box.
		expect(heard.map((el) => el.textContent!.trim())).toEqual(['Case 3:']);
		expect(designators(tag)).toEqual([]);
	});

	it('shows several numbers in one box, heard "Cases 4, 5 and 6:"', () => {
		render(CaseTag, { tag: [4, 5, 6] });
		const { box, heard } = parts();
		expect(box!.textContent!.replace(/\s+/g, ' ').trim()).toBe('4, 5, 6');
		expect(heard.map((el) => el.textContent!.trim())).toEqual(['Cases 4, 5 and 6:']);
	});

	it('hides the base case’s "Base" wholly: "Base case" beside it says it', () => {
		const { element, anchor } = label('Base case (shown)');
		render(CaseTag, { target: element, anchor, props: { tag: 'Base' } });
		const { tag, box, heard } = parts(element);
		expect(tag).toHaveAttribute('aria-hidden', 'true');
		expect(box).toBe(tag);
		expect(tag.textContent!.trim()).toBe('Base');
		expect(outOfSight(tag)).toBe(false);
		expect(heard).toEqual([]);
		expect(screen.getByRole('checkbox')).toHaveAccessibleName('Base case (shown)');
	});

	it('keeps a checkbox’s visible words in its name, the number before them (WCAG 2.5.3)', () => {
		const { element, anchor, words } = label('Pump PB off');
		render(CaseTag, { target: element, anchor, props: { tag: 2 } });
		expect(screen.getByRole('checkbox')).toHaveAccessibleName('Case 2: Pump PB off');
		// The tag before the name, so the box reads first, as it is seen.
		const tag = element.querySelector('[data-case-tag]')!;
		expect(tag.compareDocumentPosition(words) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		// Several numbers: one box, its words before the name.
		document.body.innerHTML = '';
		const merged = label('Pump PA off and Pump PB off');
		render(CaseTag, { target: merged.element, anchor: merged.anchor, props: { tag: [1, 5] } });
		expect(screen.getByRole('checkbox')).toHaveAccessibleName(
			'Cases 1 and 5: Pump PA off and Pump PB off'
		);
	});
});
