export function usePathCalculator() {
	let pathD = $state("");
	let svgDimensions = $state({ width: 0, height: 0 });

	function calculatePath(
		containerRef,
		fromRef,
		toRef,
		curvature,
		startXOffset,
		startYOffset,
		endXOffset,
		endYOffset
	) {
		if (!containerRef || !fromRef || !toRef) return;

		const containerRect = containerRef.getBoundingClientRect();
		const rectA = fromRef.getBoundingClientRect();
		const rectB = toRef.getBoundingClientRect();

		const svgWidth = containerRect.width;
		const svgHeight = containerRect.height;
		svgDimensions = { width: svgWidth, height: svgHeight };

		const startX = rectA.left - containerRect.left + rectA.width / 2 + startXOffset;
		const startY = rectA.top - containerRect.top + rectA.height / 2 + startYOffset;
		const endX = rectB.left - containerRect.left + rectB.width / 2 + endXOffset;
		const endY = rectB.top - containerRect.top + rectB.height / 2 + endYOffset;

		const controlY = startY - curvature;
		const d = `M ${startX},${startY} Q ${(startX + endX) / 2},${controlY} ${endX},${endY}`;
		pathD = d;
	}

	return {
		get pathD() {
			return pathD;
		},
		get svgDimensions() {
			return svgDimensions;
		},
		calculatePath,
	};
}