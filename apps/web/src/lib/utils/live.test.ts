import { describe, expect, it, vi } from 'vitest';
import { afterTwoFrames } from './live';

describe('afterTwoFrames', () => {
	it('writes after two frames, and not once cancelled', async () => {
		const write = vi.fn();
		afterTwoFrames(write);
		expect(write).not.toHaveBeenCalled();
		await vi.waitFor(() => expect(write).toHaveBeenCalledOnce());
		const never = vi.fn();
		afterTwoFrames(never)();
		await new Promise((resolve) => setTimeout(resolve, 20));
		expect(never).not.toHaveBeenCalled();
	});
});
