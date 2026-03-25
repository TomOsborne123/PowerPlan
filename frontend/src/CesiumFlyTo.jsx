import { useEffect, useRef } from 'react'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import {
  Viewer,
  Cartesian3,
  Color,
  OpenStreetMapImageryProvider,
} from 'cesium'

export function CesiumFlyTo({ latitude, longitude, active, onReady }) {
  const containerRef = useRef(null)
  const viewerRef = useRef(null)
  const readyRef = useRef(false)

  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return

    const viewer = new Viewer(containerRef.current, {
      animation: false,
      timeline: false,
      homeButton: false,
      geocoder: false,
      sceneModePicker: false,
      baseLayerPicker: false,
      navigationHelpButton: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      // Keep it lightweight; we only need the globe + camera.
      requestRenderMode: true,
      maximumRenderTimeChange: Infinity,
    })

    // Improve visual crispness on HiDPI displays.
    // Rendering above 2x can be expensive; cap it.
    viewer.resolutionScale = Math.min(2, window.devicePixelRatio || 1)
    viewer.scene.fxaa = true

    // Ask Cesium to refine tiles more aggressively (less blurry at this size).
    // Lower values => higher detail (more requests).
    viewer.scene.globe.maximumScreenSpaceError = 1

    // Smooth, lightweight basemap (no ion token needed).
    viewer.imageryLayers.removeAll()
    viewer.imageryLayers.addImageryProvider(new OpenStreetMapImageryProvider())

    // Keep a neutral starting view.
    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(0, 20, 18_000_000),
    })
    viewer.scene.requestRender()

    // Wait until initial tiles/frame are ready before we "show" the panel.
    const markReady = () => {
      if (readyRef.current) return
      readyRef.current = true
      if (typeof onReady === 'function') onReady()
    }

    // Fallback: never block UI if tiles/events don't behave as expected.
    const fallbackTimer = setTimeout(() => {
      viewer.scene.requestRender()
      markReady()
    }, 900)

    const removeTileListener = viewer.scene.globe.tileLoadProgressEvent.addEventListener((remaining) => {
      if (remaining === 0) {
        // Give Cesium a moment to render the first fully-loaded frame.
        setTimeout(() => {
          viewer.scene.requestRender()
          markReady()
        }, 50)
      }
    })

    // Another fallback: first render tick.
    const removePostRender = viewer.scene.postRender.addEventListener(() => {
      viewer.scene.requestRender()
      markReady()
      try {
        removePostRender?.()
      } catch {
        // ignore
      }
    })

    viewerRef.current = viewer

    return () => {
      try {
        clearTimeout(fallbackTimer)
        try {
          removeTileListener?.()
        } catch {
          // ignore
        }
        try {
          removePostRender?.()
        } catch {
          // ignore
        }
        viewer.destroy()
      } finally {
        viewerRef.current = null
      }
    }
  }, [onReady])

  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    if (!active) return
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return

    const lon = Number(longitude)
    const lat = Number(latitude)

    viewer.entities.removeAll()
    viewer.entities.add({
      position: Cartesian3.fromDegrees(lon, lat),
      point: {
        pixelSize: 10,
        color: Color.fromCssColorString('#ffb347'),
        outlineColor: Color.WHITE,
        outlineWidth: 2,
      },
    })

    viewer.camera.flyTo({
      // Zoom to town/village scale (meters above ellipsoid).
      destination: Cartesian3.fromDegrees(lon, lat, 45_000),
      duration: 1.8,
    })
    viewer.scene.requestRender()
  }, [latitude, longitude, active])

  return <div ref={containerRef} className="scrape-globe-cesium" aria-hidden="true" />
}

