"use client";

import {
  Card,
  Descriptions,
  List,
  Progress,
  Space,
  Tag,
  Typography
} from "antd";
import {
  CheckCircleOutlined,
  DollarOutlined,
  RocketOutlined,
  StarOutlined,
  StockOutlined,
  TrophyOutlined
} from "@ant-design/icons";
import type { RecommendationExplanation, RecommendationItemExplanation } from "@/lib/types";
import { currency } from "@/lib/format";
import { useLanguage } from "@/lib/i18n";

function ratingColor(rating: number): string {
  if (rating >= 4.5) return "green";
  if (rating >= 4.0) return "blue";
  if (rating >= 3.0) return "orange";
  return "red";
}

function InsightCard({
  icon,
  title,
  content,
  color
}: {
  icon: React.ReactNode;
  title: string;
  content: string;
  color?: string;
}) {
  return (
    <Card size="small" style={{ marginBottom: 8 }}>
      <Space>
        <Typography.Text style={{ fontSize: 16 }}>{icon}</Typography.Text>
        <Typography.Text strong>{title}</Typography.Text>
      </Space>
      <Typography.Paragraph
        type={color === "danger" ? "danger" : color === "warning" ? "warning" : "secondary"}
        style={{ marginTop: 6, marginBottom: 0 }}
      >
        {content}
      </Typography.Paragraph>
    </Card>
  );
}

export default function RecommendationExplanationCard({
  explanation
}: {
  explanation?: RecommendationExplanation | null;
}) {
  const { t, translateStatus } = useLanguage();

  if (!explanation) return null;

  const budgetColor =
    explanation.budget_status === "over_budget" ? "red" : "green";

  return (
    <Card
      title={
        <Space>
          <TrophyOutlined />
          <span>{t("insights.rationale")}</span>
        </Space>
      }
      size="small"
      style={{ marginTop: 8 }}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        {/* Summary */}
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          {explanation.summary}
        </Typography.Paragraph>

        {/* Item explanations */}
        <List
          size="small"
          dataSource={explanation.item_explanations}
          renderItem={(item: RecommendationItemExplanation) => (
            <List.Item>
              <List.Item.Meta
                avatar={
                  <Tag color={ratingColor(item.rating)}>
                    <StarOutlined /> {item.rating}
                  </Tag>
                }
                title={
                  <Space wrap>
                    <Typography.Text strong>{item.name}</Typography.Text>
                    <Typography.Text type="secondary">
                      ${item.price.toFixed(2)}
                    </Typography.Text>
                  </Space>
                }
                description={item.why_recommended}
              />
            </List.Item>
          )}
        />

        {/* Insights */}
        <Space direction="vertical" size={4} style={{ width: "100%" }}>
          <InsightCard
            icon={<DollarOutlined />}
            title={t("insights.budget")}
            content={explanation.budget_insight}
            color={budgetColor}
          />
          <InsightCard
            icon={<RocketOutlined />}
            title={t("insights.delivery")}
            content={explanation.delivery_insight}
          />
          <InsightCard
            icon={<StockOutlined />}
            title={t("insights.stock")}
            content={explanation.stock_insight}
          />
          <InsightCard
            icon={<TrophyOutlined />}
            title={t("insights.ranking")}
            content={explanation.ranking_rationale}
          />
        </Space>
      </Space>
    </Card>
  );
}
