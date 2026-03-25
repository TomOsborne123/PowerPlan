import { useEffect, useRef } from 'react'
import * as am5 from '@amcharts/amcharts5'
import * as am5map from '@amcharts/amcharts5/map'
import am5geodata_worldLow from '@amcharts/amcharts5-geodata/worldLow'

export function ScrapeGlobe({ latitude, longitude, spinning }) {
  const containerRef = useRef(null)
  const rootRef = useRef(null)
  const chartRef = useRef(null)
  const pointSeriesRef = useRef(null)
  const spinTimerRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || rootRef.current) return

    const root = am5.Root.new(containerRef.current)
    rootRef.current = root

    // Remove the default amCharts "logo/credits" overlay.
    // amCharts attaches it to `root._logo`; disposing it hides the watermark/link.
    try {
      if (root && root._logo) {
        root._logo.dispose()
      }
    } catch {
      // Non-fatal: if internals change, credits may still show but globe will work.
    }

    const chart = root.container.children.push(
      am5map.MapChart.new(root, {
        panX: 'none',
        panY: 'none',
        wheelY: 'none',
        projection: am5map.geoOrthographic(),
      }),
    )
    chartRef.current = chart

    chart.series.push(
      am5map.MapPolygonSeries.new(root, {
        geoJSON: am5geodata_worldLow,
        fill: am5.color(0x4fa966),
        stroke: am5.color(0x0f131a),
        strokeWidth: 0.5,
      }),
    )

    const points = chart.series.push(
      am5map.MapPointSeries.new(root, {
        latitudeField: 'latitude',
        longitudeField: 'longitude',
      }),
    )
    pointSeriesRef.current = points

    points.bullets.push(() => {
      const pulse = am5.Circle.new(root, {
        radius: 8,
        fill: am5.color(0xffb347),
        fillOpacity: 0.15,
        stroke: am5.color(0xffb347),
        strokeOpacity: 0.95,
        strokeWidth: 2,
      })
      pulse.animate({
        key: 'scale',
        from: 0.9,
        to: 2.8,
        duration: 1200,
        loops: Infinity,
        easing: am5.ease.out(am5.ease.cubic),
      })
      pulse.animate({
        key: 'opacity',
        from: 0.95,
        to: 0.05,
        duration: 1200,
        loops: Infinity,
        easing: am5.ease.out(am5.ease.cubic),
      })

      const core = am5.Circle.new(root, {
        radius: 4.5,
        fill: am5.color(0xffb347),
        stroke: am5.color(0xffffff),
        strokeWidth: 2,
      })

      const container = am5.Container.new(root, {})
      container.children.push(pulse)
      container.children.push(core)

      return am5.Bullet.new(root, { sprite: container })
    })

    chart.set('background', am5.Rectangle.new(root, { fillOpacity: 0 }))

    return () => {
      if (spinTimerRef.current) {
        window.clearInterval(spinTimerRef.current)
        spinTimerRef.current = null
      }
      root.dispose()
      rootRef.current = null
      chartRef.current = null
      pointSeriesRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    const points = pointSeriesRef.current
    if (!chart || !points) return
    points.data.setAll(
      Number.isFinite(latitude) && Number.isFinite(longitude)
        ? [{ longitude: Number(longitude), latitude: Number(latitude) }]
        : [],
    )
  }, [latitude, longitude])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    if (spinTimerRef.current) {
      window.clearInterval(spinTimerRef.current)
      spinTimerRef.current = null
    }

    if (spinning) {
      // While spinning, keep a wider global view.
      chart.set('zoomLevel', 1)
      spinTimerRef.current = window.setInterval(() => {
        const current = Number(chart.get('rotationX') || 0)
        chart.set('rotationX', current + 2)
      }, 30)
      return
    }

    if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
      // Land on the user pin and zoom in.
      chart.animate({ key: 'rotationX', to: -Number(longitude), duration: 650, easing: am5.ease.out(am5.ease.cubic) })
      chart.animate({ key: 'rotationY', to: Number(latitude), duration: 650, easing: am5.ease.out(am5.ease.cubic) })
      chart.animate({ key: 'zoomLevel', to: 1.9, duration: 650, easing: am5.ease.out(am5.ease.cubic) })
    } else {
      // If no coordinates, freeze with default zoom.
      chart.set('zoomLevel', 1)
    }
  }, [spinning, latitude, longitude])

  return <div ref={containerRef} className="scrape-globe-amchart" aria-hidden="true" />
}

