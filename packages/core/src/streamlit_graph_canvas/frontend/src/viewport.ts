/** Keep v12's ratio padding when v13 interprets numeric padding as pixels. */
export function fitViewPadding(ratio: number): `${number}%` {
  return `${(ratio / (1 + ratio)) * 50}%`;
}
