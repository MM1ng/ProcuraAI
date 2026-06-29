"use client";

import { App, Button, Popover, Space, Tag, Typography } from "antd";
import { CopyOutlined, RobotOutlined, UserOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";
import { useLanguage } from "@/lib/i18n";
import { currency } from "@/lib/format";
import type { ProductRetrievalEvidence, RetrievalEvidence } from "@/lib/types";

type ChatMessageProps = {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  createdAt?: string;
  retrievalEvidence?: RetrievalEvidence;
};

const SOURCE_PATTERN = /\[来源(\d+)\]/g;
const CHANNEL_COLORS: Record<string, string> = {
  vector: "purple",
  bm25: "green",
  hybrid: "gold",
};

function renderValue(value: unknown) {
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

function SourcePopoverContent({ product }: { product: ProductRetrievalEvidence }) {
  return (
    <Space direction="vertical" size={6} style={{ maxWidth: 280 }}>
      <Typography.Text strong>{renderValue(product.name)}</Typography.Text>
      <Typography.Text type="secondary">ID: {renderValue(product.product_id)}</Typography.Text>
      <Space wrap size={[6, 4]}>
        <Tag color="blue">{renderValue(product.brand)}</Tag>
        <Tag>{typeof product.price === "number" ? currency(product.price) : "-"}</Tag>
        <Tag color="orange">Rating {renderValue(product.rating)}</Tag>
      </Space>
      {product.retrieval_channels?.length ? (
        <Space wrap size={[6, 4]}>
          {product.retrieval_channels.map((channel) => (
            <Tag key={channel} color={CHANNEL_COLORS[channel] || "default"}>{channel}</Tag>
          ))}
        </Space>
      ) : null}
    </Space>
  );
}

function renderContentWithSources(content: string, evidence?: RetrievalEvidence) {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;

  for (const match of content.matchAll(SOURCE_PATTERN)) {
    const fullMatch = match[0];
    const sourceIndex = Number(match[1]);
    const start = match.index ?? 0;
    const product = evidence?.products?.[sourceIndex - 1];
    const sourceNode = (
      <sup className="source-citation" key={`source-${start}-${sourceIndex}`} tabIndex={product ? 0 : undefined}>
        来源{sourceIndex}
      </sup>
    );

    if (start > lastIndex) nodes.push(content.slice(lastIndex, start));
    nodes.push(product ? (
      <Popover key={`popover-${start}-${sourceIndex}`} content={<SourcePopoverContent product={product} />} trigger={["hover", "click"]} placement="top">
        {sourceNode}
      </Popover>
    ) : sourceNode);
    lastIndex = start + fullMatch.length;
  }

  if (lastIndex < content.length) nodes.push(content.slice(lastIndex));
  return nodes.length ? nodes : content;
}

export default function ChatMessage({ role, content, streaming, createdAt: _createdAt, retrievalEvidence }: ChatMessageProps) {
  const { t } = useLanguage();
  const { message } = App.useApp();

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      message.success(t("chat.copied"));
    } catch {
      message.error(t("chat.copyFailed"));
    }
  };

  return (
    <div className={`chat-row ${role === "user" ? "is-user" : "is-agent"}`}>
      <div className="chat-avatar">
        {role === "user" ? <UserOutlined /> : <RobotOutlined />}
      </div>
      <div className="chat-bubble">
        <div className="chat-header">
          <div className="chat-role">
            {role === "user" ? t("chat.requester") : t("chat.agent")}
          </div>
          <Button
            className="copy-btn"
            type="text"
            size="small"
            icon={<CopyOutlined />}
            onClick={handleCopy}
            aria-label={t("chat.copy")}
          />
        </div>
        <div className="chat-content">
          {role === "assistant" ? renderContentWithSources(content, retrievalEvidence) : content}
          {streaming ? <span className="stream-cursor" /> : null}
        </div>
      </div>
    </div>
  );
}
