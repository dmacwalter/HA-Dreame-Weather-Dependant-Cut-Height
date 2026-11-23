"""Source precedence, including a snapshot taken from the live Townsville setup."""
from custom_components.dreame_smart_cut_height.plan import plan
from custom_components.dreame_smart_cut_height.weather import merge_weather_sources
from custom_components.dreame_smart_cut_height.zones import option_for, zone_id, zone_name, zones_from_options

P = {"grow": 23, "heavy_rain": 25, "hot_max": 34, "t95": 29.5, "dry_bucket": -15, "dry_deficit": 60,
     "rain_offset": -.5, "hot_offset": .5, "wave_offset": 1, "dry_season_offset": .5}


def test_live_townsville_snapshot_matches_existing_jinja_plan():
    times=[f"2026-11-{d:02d}" for d in range(2,29)]
    daily={
      "time":times,
      "temperature_2m_mean":[27.4,27.6,27.7,27.8,28.1,28.2,28.4,28.8,28.6,28.6,28.3,27.9,27.8,28.3,28.6,28.8,28.2,27.3,25.6,26.6,26.6,26.3,25.6,26.3,27.3,27.1,27.3],
      "temperature_2m_max":[29.9,30.3,29.9,30.7,32,31.2,31.2,31.4,31.2,31.2,31,30.9,30.8,30.8,31.5,32.1,30.8,30.6,27.5,29.3,29.6,30.1,29.5,31,32,29.8,29.6],
      "temperature_2m_min":[25.6,25.5,26,25.2,24.9,25.9,26.7,26.6,26.7,26.2,26.1,25.7,25.7,26.6,26.7,25.3,25.4,23.4,24.1,23.6,24.1,22.7,21.6,21.6,23.7,23.9,25],
      "precipitation_sum":[0.1,0.4,0.6,0.4,0,0,0,0.3,0.4,0,0,0,0,0.1,0,0.2,1.3,5.1,20.1,0.2,1.5,0,0,0,6.5,1.1,1.4],
      "et0_fao_evapotranspiration":[5.26,5.59,5.37,5.16,5.97,5.65,6.09,6.21,6.44,6.22,6.05,6.57,6.24,5,5.93,5.78,5.48,5.23,3.29,5.25,5.83,6.06,6.09,5.9,5.58,5.34,4.94],
    }
    raw_station=[
      (30.8,24.3,27.05,.8),(31,26,27.99,0),(30.9,25.6,27.87,0),(31.1,25.7,27.93,0),(31.3,24.8,27.47,0),(32.4,23.7,27.88,0),(31.6,26,28.22,0),(31.7,25.9,28.01,0),(31.9,25.4,28.31,0),(30.8,26.8,28.2,0),(30.9,26.1,27.93,0),(30.7,26,27.84,0),(30.2,25.6,27.44,0),(30.6,25.5,27.47,0),(30.3,24.9,27.3,0),(31.6,25.7,28.04,0),(31.9,25.6,28.5,0),(31.4,26.1,28.2,0),(30.9,24.3,27.42,5),(27.6,23.5,25.17,10.6),(30.7,23.9,26.97,1.9),(30.7,24.1,27.13,1.6),(30,24.1,26.98,1.1),
    ]
    station={f"2026-11-{i:02d}":{"max":a,"min":b,"mean":c,"rain":d} for i,(a,b,c,d) in enumerate(raw_station,1)}
    bom=[{"datetime":f"2026-11-{d:02d}T00:00:00+10:00","temperature":mx,"templow":mn} for d,mx,mn in [(23,31,22),(24,31,22),(25,31,22),(26,31,23),(27,31,25),(28,31,25)]]
    merged,station_days,bom_days=merge_weather_sources(daily,bom,station,21)
    assert (station_days,bom_days)==(21,6)
    result = plan(daily=merged, i=21, today="2026-11-23", bucket=2.09, local_rain=0, heat_warning=False, p=P)
    assert result=={"t7":27.1,"rain3":4.6,"deficit":99.2,"ehi":-2.4,"wet_season":True,"growing":True,"heavy":False,"hot":False,"wave":False,"dry":False,"rain_until":"1970-01-01","heat_until":"1970-01-01","wave_until":"1970-01-01","offset":0.0,"why":"normal","can_lower":True}


def test_station_temperature_requires_max_min_and_mean_but_rain_is_independent():
    daily={"time":["2026-01-01","2026-01-02"],"temperature_2m_mean":[20,21],"temperature_2m_max":[25,26],"temperature_2m_min":[15,16],"precipitation_sum":[1,2],"et0_fao_evapotranspiration":[3,4]}
    station={"2026-01-01":{"max":30,"min":20,"rain":8},"2026-01-02":{"max":31,"min":21,"rain":9}}
    merged,station_days,bom_days=merge_weather_sources(daily,[],station,1)
    assert station_days==0 and bom_days==0
    assert merged["temperature_2m_max"]==[25,26]
    assert merged["precipitation_sum"]==[8,9]


def test_bom_is_used_for_today_and_forecast_but_not_past():
    daily={"time":["2026-01-01","2026-01-02","2026-01-03"],"temperature_2m_mean":[20,21,22],"temperature_2m_max":[25,26,27],"temperature_2m_min":[15,16,17],"precipitation_sum":[1,2,3],"et0_fao_evapotranspiration":[3,4,5]}
    bom=[{"datetime":"2026-01-01T00:00:00","temperature":35,"templow":25},{"datetime":"2026-01-02T00:00:00","temperature":36,"templow":26},{"datetime":"2026-01-03T00:00:00","temperature":37,"templow":27}]
    merged,_,bom_days=merge_weather_sources(daily,bom,{},1)
    assert bom_days==2
    assert merged["temperature_2m_max"]==[25,36,37]


def test_zone_labels_from_the_dreame_selector():
    live = ["Raised Lawn (#1)", "Orchard (#2)", "Front Yard (#3)", "Nature Strip (#4)"]
    assert [zone_id(o) for o in live] == [1, 2, 3, 4]
    assert zone_name("Raised Lawn (#1)") == "Raised Lawn"
    assert zone_id("Zone #3") == 3 and zone_name("Zone #3") == "Zone #3"
    assert zone_id("Whole map") is None
    assert zones_from_options(live)[0] == {"id": 1, "name": "Raised Lawn"}


def test_renamed_zone_is_found_by_id_and_missing_zones_are_kept():
    before = zones_from_options(["Raised Lawn (#1)", "Zone #3"])
    after = zones_from_options(["Raised Lawn (#1)", "Front Yard (#3)"], before)
    assert [z["name"] for z in after] == ["Raised Lawn", "Front Yard"]
    assert option_for(["Raised Lawn (#1)", "Front Yard (#3)"], 3) == "Front Yard (#3)"
    kept = zones_from_options([], after)
    assert [z["id"] for z in kept] == [1, 3]
