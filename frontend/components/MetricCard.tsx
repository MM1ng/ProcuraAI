import { Card, Statistic } from "antd";

export default function MetricCard({
  title,
  value,
  suffix
}: {
  title: string;
  value: string | number;
  suffix?: string;
}) {
  return (
    <Card size="small">
      <Statistic title={title} value={value} suffix={suffix} />
    </Card>
  );
}
