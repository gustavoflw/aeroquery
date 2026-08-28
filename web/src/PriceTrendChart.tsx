import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { PRICE_TREND_TOTAL_DAYS, buildPriceTrendChartFigure } from './trendChartMath'
import type { CheapestDirect, ConfigResponse, TrendStat } from './types'

interface PriceTrendChartProps {
  trend: TrendStat[]
  centerDate: string
  currency: string
  config: ConfigResponse
  cheapestDirect: CheapestDirect | null
  xRange: [string, string]
}

export function PriceTrendChart({
  trend,
  centerDate,
  currency,
  config,
  cheapestDirect,
  xRange,
}: PriceTrendChartProps) {
  const figure = useMemo(
    () =>
      buildPriceTrendChartFigure(
        trend,
        centerDate,
        currency,
        config.map_style,
        config.currency_symbols,
        config.neon_bg,
        cheapestDirect,
        xRange,
      ),
    [trend, centerDate, currency, config, cheapestDirect, xRange],
  )

  const foundDays = trend.filter((r) => r.mean !== null).length

  return (
    <div className="price-trend">
      <h2>📈 Price trend — {PRICE_TREND_TOTAL_DAYS} days</h2>
      <Plot
        data={figure.data}
        layout={{ ...figure.layout, autosize: true }}
        style={{ width: '100%', height: '340px' }}
        useResizeHandler
        config={{ displaylogo: false }}
      />
      <p className="trend-caption">
        {foundDays} of {trend.length} days had available fares · vertical bars reach from the
        average up to that day's highest fare and down to its lowest · marker color scales from
        cheapest (green) to priciest (red).
        {cheapestDirect === null && ' No nonstop flights found anywhere in this window (yet).'}
      </p>
    </div>
  )
}
