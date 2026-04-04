import { onMount } from "svelte";

export function useResizeObserver(getContainerRef, callback) {
	onMount(() => {
		const containerRef = getContainerRef();
		if (!containerRef) return;

		const resizeObserver = new ResizeObserver(() => {
			callback();
		});

		resizeObserver.observe(containerRef);

		// Initial call
		callback();

		return () => {
			resizeObserver.disconnect();
		};
	});
}