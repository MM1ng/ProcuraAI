"use client";

import ProductTable from "@/components/ProductTable";
import { useLanguage } from "@/lib/i18n";

export default function ProductsPage() {
  const { t } = useLanguage();

  return (
    <main className="page">
      <div className="page-header">
        <h1 className="page-title">{t("products.title")}</h1>
      </div>
      <ProductTable />
    </main>
  );
}
