export function currency(value: number | undefined | null) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2
  }).format(value ?? 0);
}

export function percent(value: number | undefined | null) {
  return `${Math.round((value ?? 0) * 100)}%`;
}
