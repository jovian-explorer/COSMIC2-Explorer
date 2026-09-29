"""Planetary Body and Mission Registry for VEDA.

Maintains authoritative physical constants, atmospheric properties, and
spacecraft mission definitions across NASA, ESA, JAXA, and NOAA planetary programs.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from .models import BodyInfo, InstrumentInfo, MissionInfo


# ===========================================================================
# PLANETARY BODIES & MOONS
# ===========================================================================

BODIES: Dict[str, BodyInfo] = {
    "venus": BodyInfo(
        id="venus",
        name="Venus",
        category="terrestrial_planet",
        radius_km=6051.8,
        surface_gravity=8.87,
        mean_molecular_weight=43.45,  # 96.5% CO2, 3.5% N2
        gas_constant_r=191.4,         # J / (kg K)
        isobaric_heat_capacity_cp=850.0,
        reference_pressure_hpa=92000.0,  # ~92 bar surface pressure
        atmospheric_composition={"CO2": 96.5, "N2": 3.5, "SO2": 0.015},
        description="Terrestrial planet with a massive, superrotating CO2 atmosphere and sulphuric acid cloud decks.",
        supported_missions=["akatsuki", "vex", "bepicolombo"],
    ),
    "earth": BodyInfo(
        id="earth",
        name="Earth",
        category="terrestrial_planet",
        radius_km=6371.0,
        surface_gravity=9.80665,
        mean_molecular_weight=28.97,  # 78% N2, 21% O2, 1% Ar
        gas_constant_r=287.058,
        isobaric_heat_capacity_cp=1004.6,
        reference_pressure_hpa=1000.0,
        atmospheric_composition={"N2": 78.08, "O2": 20.95, "Ar": 0.93, "H2O": 1.0},
        description="Our home planet; dense tropical GNSS radio occultation atmospheric and ionospheric profiling.",
        supported_missions=["cosmic2"],
    ),
    "mars": BodyInfo(
        id="mars",
        name="Mars",
        category="terrestrial_planet",
        radius_km=3389.5,
        surface_gravity=3.72,
        mean_molecular_weight=43.34,  # 95% CO2, 2.6% N2, 1.9% Ar
        gas_constant_r=191.8,
        isobaric_heat_capacity_cp=830.0,
        reference_pressure_hpa=6.1,  # ~610 Pa surface pressure
        atmospheric_composition={"CO2": 95.32, "N2": 2.6, "Ar": 1.9, "O2": 0.13},
        description="Thin CO2 atmosphere with extensive seasonal polar cycling and atmospheric escape.",
        supported_missions=["maven"],
    ),
    "jupiter": BodyInfo(
        id="jupiter",
        name="Jupiter",
        category="gas_giant",
        radius_km=69911.0,
        surface_gravity=24.79,
        mean_molecular_weight=2.22,  # 89% H2, 10% He
        gas_constant_r=3745.0,
        isobaric_heat_capacity_cp=12360.0,
        reference_pressure_hpa=1000.0,  # 1 bar reference level
        atmospheric_composition={"H2": 89.8, "He": 10.2, "CH4": 0.3},
        description="Largest planet in solar system; deep hydrogen atmosphere with prominent zonal jet streams and Great Red Spot.",
        supported_missions=["juno", "galileo", "cassini", "new_horizons"],
    ),
    "saturn": BodyInfo(
        id="saturn",
        name="Saturn",
        category="gas_giant",
        radius_km=58232.0,
        surface_gravity=10.44,
        mean_molecular_weight=2.07,  # 96% H2, 3% He
        gas_constant_r=4016.0,
        isobaric_heat_capacity_cp=14000.0,
        reference_pressure_hpa=1000.0,  # 1 bar reference level
        atmospheric_composition={"H2": 96.3, "He": 3.25, "CH4": 0.45},
        description="Ringed gas giant with high-velocity equatorial jets, polar vortices, and rich satellite system.",
        supported_missions=["cassini"],
    ),
    "titan": BodyInfo(
        id="titan",
        name="Titan",
        category="moon",
        radius_km=2574.7,
        surface_gravity=1.352,
        mean_molecular_weight=28.6,  # 95% N2, 5% CH4
        gas_constant_r=290.7,
        isobaric_heat_capacity_cp=1040.0,
        reference_pressure_hpa=1467.0,  # 1.47 bar surface pressure
        atmospheric_composition={"N2": 95.0, "CH4": 4.9, "H2": 0.1},
        description="Largest moon of Saturn with dense nitrogen-methane atmosphere and liquid hydrocarbon lakes.",
        supported_missions=["cassini"],
    ),
    "pluto": BodyInfo(
        id="pluto",
        name="Pluto",
        category="dwarf_planet",
        radius_km=1188.3,
        surface_gravity=0.62,
        mean_molecular_weight=28.01,  # >99% N2
        gas_constant_r=296.8,
        isobaric_heat_capacity_cp=1039.0,
        reference_pressure_hpa=0.0115,  # ~1.15 Pa (11.5 microbar) surface pressure
        atmospheric_composition={"N2": 99.0, "CH4": 0.5, "CO": 0.1},
        description="Kuiper belt dwarf planet with nitrogen atmosphere, haze layers, and active glacial plains (Sputnik Planitia).",
        supported_missions=["new_horizons"],
    ),
    "mercury": BodyInfo(
        id="mercury",
        name="Mercury",
        category="terrestrial_planet",
        radius_km=2439.7,
        surface_gravity=3.7,
        mean_molecular_weight=20.0,
        gas_constant_r=415.7,
        isobaric_heat_capacity_cp=1000.0,
        reference_pressure_hpa=1e-12,
        atmospheric_composition={"O": 42.0, "Na": 29.0, "H": 22.0, "He": 6.0},
        description="Innermost planet with a dynamic exosphere and strong solar wind interactions.",
        supported_missions=["bepicolombo"],
    ),
}


# ===========================================================================
# SPACECRAFT MISSIONS
# ===========================================================================

MISSIONS: Dict[str, MissionInfo] = {
    "cosmic2": MissionInfo(
        id="cosmic2",
        name="COSMIC-2",
        agency="NOAA / UCAR / TACC / NASA",
        launch_date="2019-06-25",
        mission_status="operational",
        primary_targets=["earth"],
        instruments=[
            InstrumentInfo(id="TGRS", name="TriG GNSS Radio Occultation Receiver", instrument_type="radio_science",
                           measurement_targets=["neutral_atmosphere", "ionosphere"],
                           description="Dual-frequency GPS and GLONASS radio occultation sensor tracking refractivity, temperature, water vapour, and electron density."),
            InstrumentInfo(id="IVM", name="Ion Velocity Meter", instrument_type="plasma",
                           measurement_targets=["ionosphere", "plasma"],
                           description="In-situ measurement of ion drift, density, and temperature at low Earth orbit."),
        ],
        authoritative_archive="UCAR COSMIC Data Analysis and Archive Center (CDAAC)",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        citation="UCAR/CDAAC COSMIC-2 Post-Processed and Near-Real-Time Data Products (2020-present).",
        description="Six-satellite constellation in 24° low-inclination orbit providing ~5,000 daily high-precision tropical atmospheric and ionospheric soundings.",
    ),
    "akatsuki": MissionInfo(
        id="akatsuki",
        name="Akatsuki (VCO)",
        agency="JAXA / ISAS",
        launch_date="2010-05-20",
        mission_status="completed",
        primary_targets=["venus"],
        instruments=[
            InstrumentInfo(id="RS", name="Radio Science Experiment", instrument_type="radio_science",
                           measurement_targets=["neutral_atmosphere"],
                           description="X-band radio occultation sounding Venus vertical temperature, pressure, refractivity, and static stability."),
            InstrumentInfo(id="UVI", name="Ultraviolet Imager", instrument_type="camera",
                           measurement_targets=["cloud_tops", "SO2"],
                           description="283 nm and 365 nm imaging tracking cloud-top wind vectors and SO2 distributions."),
            InstrumentInfo(id="LIR", name="Longwave Infrared Camera", instrument_type="camera",
                           measurement_targets=["cloud_tops", "thermal"],
                           description="10 micron uncooled microbolometer camera imaging cloud-top temperatures on day and night sides."),
            InstrumentInfo(id="IR1", name="1-Micron Camera", instrument_type="camera",
                           measurement_targets=["surface", "lower_clouds"],
                           description="Near-infrared camera imaging surface thermal emission and lower cloud dynamics."),
            InstrumentInfo(id="IR2", name="2-Micron Camera", instrument_type="camera",
                           measurement_targets=["middle_lower_clouds", "CO"],
                           description="Multi-band camera probing middle and lower clouds and carbon monoxide abundance."),
        ],
        authoritative_archive="JAXA DARTS / NASA PDS Atmospheres Node",
        archive_url="https://data.darts.isas.jaxa.jp/pub/pds3/",
        citation="Imamura, T., et al. (2017). Initial performance of the radio occultation experiment aboard Akatsuki. Earth, Planets and Space, 69(1), 137.",
        description="Japan's Venus Climate Orbiter dedicated to understanding the super-rotation and 3D dynamics of Venus' atmosphere.",
    ),
    "new_horizons": MissionInfo(
        id="new_horizons",
        name="New Horizons",
        agency="NASA / JHUAPL / SwRI",
        launch_date="2006-01-19",
        mission_status="operational",
        primary_targets=["pluto", "jupiter"],
        instruments=[
            InstrumentInfo(id="REX", name="Radio Science Experiment", instrument_type="radio_science",
                           measurement_targets=["neutral_atmosphere", "surface_pressure"],
                           description="Uplink radio occultation measuring Pluto's surface pressure, temperature profile, and ionosphere."),
            InstrumentInfo(id="LORRI", name="Long Range Reconnaissance Imager", instrument_type="camera",
                           measurement_targets=["surface", "haze"],
                           description="Panchromatic high-resolution visible telescope imaging Pluto, Charon, Arrokoth, and Kuiper belt objects."),
            InstrumentInfo(id="MVIC", name="Multispectral Visible Imaging Camera (Ralph)", instrument_type="camera",
                           measurement_targets=["surface", "color"],
                           description="4-color and panchromatic imaging camera mapping composition and color."),
            InstrumentInfo(id="SWAP", name="Solar Wind Around Pluto", instrument_type="plasma",
                           measurement_targets=["solar_wind", "plasma"],
                           description="Solar wind analyzer measuring interaction with Pluto's escaping atmosphere."),
            InstrumentInfo(id="PEPSSI", name="Pluto Energetic Particle Spectrometer Science Investigation", instrument_type="plasma",
                           measurement_targets=["energetic_particles"],
                           description="Measures energetic ions and electrons across the outer solar system."),
            InstrumentInfo(id="SDC", name="Venetia Burney Student Dust Counter", instrument_type="dust_counter",
                           measurement_targets=["interplanetary_dust"],
                           description="Measures mass and distribution of dust grains from 1 AU beyond 55 AU."),
        ],
        authoritative_archive="NASA PDS Atmospheres / Small Bodies / Ring-Moon Systems",
        archive_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/Horizons/rex.html",
        citation="Stern, S. A., et al. (2015). The Pluto system: Initial results from its exploration by New Horizons. Science, 350(6258).",
        description="First mission to explore the Pluto-Charon system and the Kuiper Belt (Arrokoth), now exploring the outer heliosphere.",
    ),
    "juno": MissionInfo(
        id="juno",
        name="Juno",
        agency="NASA / JPL",
        launch_date="2011-08-05",
        mission_status="operational",
        primary_targets=["jupiter"],
        instruments=[
            InstrumentInfo(id="GRAVITY_RO", name="Gravity & Radio Science", instrument_type="radio_science",
                           measurement_targets=["neutral_atmosphere", "gravity"],
                           description="Radio occultation and Doppler gravity sounding of Jupiter's deep atmosphere and core."),
            InstrumentInfo(id="MWR", name="Microwave Radiometer", instrument_type="spectrometer",
                           measurement_targets=["deep_atmosphere", "ammonia", "water"],
                           description="6-channel radiometer sounding from 1 bar down to >100 bars pressure."),
            InstrumentInfo(id="JIRAM", name="Jovian InfraRed Auroral Mapper", instrument_type="camera",
                           measurement_targets=["aurora", "hotspots"],
                           description="Infrared imager and spectrometer probing upper troposphere and auroral emissions."),
            InstrumentInfo(id="JunoCam", name="JunoCam Visible Imager", instrument_type="camera",
                           measurement_targets=["cloud_tops"],
                           description="Wide-angle color camera providing high-resolution views of polar cyclones and atmospheric bands."),
        ],
        authoritative_archive="NASA PDS Atmospheres Node",
        archive_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/JUNO/juno.html",
        citation="Bolton, S. J., et al. (2017). Jupiter's interior and deep atmosphere: The initial results from the Juno mission. Science, 356(6340), 821-825.",
        description="Polar-orbiting spacecraft studying Jupiter's composition, gravity field, magnetic field, and polar magnetosphere.",
    ),
    "cassini": MissionInfo(
        id="cassini",
        name="Cassini-Huygens",
        agency="NASA / ESA / ASI",
        launch_date="1997-10-15",
        mission_status="completed",
        primary_targets=["saturn", "titan", "jupiter"],
        instruments=[
            InstrumentInfo(id="RSS", name="Radio Science Subsystem", instrument_type="radio_science",
                           measurement_targets=["neutral_atmosphere", "rings", "ionosphere"],
                           description="S-, X-, and Ka-band occultation soundings of Saturn's and Titan's vertical atmospheres and ring particle sizes."),
            InstrumentInfo(id="CIRS", name="Composite Infrared Spectrometer", instrument_type="spectrometer",
                           measurement_targets=["thermal_structure", "composition"],
                           description="Thermal infrared spectrometer measuring vertical temperature profiles and trace gas abundances."),
            InstrumentInfo(id="ISS", name="Imaging Science Subsystem", instrument_type="camera",
                           measurement_targets=["surface", "clouds", "rings"],
                           description="Narrow and wide-angle cameras capturing multi-spectral images of Saturn, Titan, and icy moons."),
        ],
        authoritative_archive="NASA PDS Atmospheres Node / Ring-Moon Systems Node",
        archive_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/Saturn/cassini_rss.html",
        citation="Flasar, F. M., et al. (2005). Titan's atmospheric temperatures, winds, and composition. Science, 308(5724), 975-978.",
        description="Fourteen-year flagship mission at Saturn, revolutionizing understanding of Saturn's atmosphere, Titan, and Enceladus.",
    ),
    "vex": MissionInfo(
        id="vex",
        name="Venus Express (VEX)",
        agency="ESA",
        launch_date="2005-11-09",
        mission_status="completed",
        primary_targets=["venus"],
        instruments=[
            InstrumentInfo(id="VeRa", name="Venus Radio Science Experiment", instrument_type="radio_science",
                           measurement_targets=["neutral_atmosphere", "ionosphere"],
                           description="Dual-frequency radio occultation sounding vertical temperature and pressure profiles between 40 and 90 km."),
            InstrumentInfo(id="VMC", name="Venus Monitoring Camera", instrument_type="camera",
                           measurement_targets=["cloud_dynamics", "airglow"],
                           description="Wide-angle camera observing Venus in UV, visible, and near-IR bands."),
            InstrumentInfo(id="VIRTIS", name="Visible and Infrared Thermal Imaging Spectrometer", instrument_type="spectrometer",
                           measurement_targets=["composition", "temperature"],
                           description="Spectrometer mapping lower and middle atmosphere composition and temperature fields."),
        ],
        authoritative_archive="ESA Planetary Science Archive (PSA) / NASA PDS Atmospheres Node",
        archive_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/VENUS/venus_express.html",
        citation="Tellmann, S., et al. (2009). Structure of the Venus neutral atmosphere as observed by the Radio Science experiment VeRa on Venus Express. JGR Planets, 114(E9).",
        description="Europe's first mission to Venus, conducting long-term global monitoring of the complex Venusian atmosphere.",
    ),
    "maven": MissionInfo(
        id="maven",
        name="MAVEN",
        agency="NASA / LASP",
        launch_date="2013-11-18",
        mission_status="operational",
        primary_targets=["mars"],
        instruments=[
            InstrumentInfo(id="RS_RO", name="Radio Occultation Science", instrument_type="radio_science",
                           measurement_targets=["ionosphere", "neutral_atmosphere"],
                           description="Occultation sounding of Martian neutral density and electron density profiles."),
            InstrumentInfo(id="NGIMS", name="Neutral Gas and Ion Mass Spectrometer", instrument_type="spectrometer",
                           measurement_targets=["upper_atmosphere", "ionosphere"],
                           description="Measures composition and vertical structure of neutral and ionized species from 120 to 500 km."),
            InstrumentInfo(id="IUVS", name="Imaging Ultraviolet Spectrograph", instrument_type="spectrometer",
                           measurement_targets=["corona", "aurora", "ozone"],
                           description="Global UV limb and nadir imaging characterizing Martian atmospheric loss."),
        ],
        authoritative_archive="NASA PDS Atmospheres Node / PPI Node",
        archive_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/MAVEN/maven.html",
        citation="Jakosky, B. M., et al. (2015). The Mars Atmosphere and Volatile Evolution (MAVEN) mission. Space Science Reviews, 195(1), 3-48.",
        description="Dedicated mission investigating the loss of Mars' atmosphere and water to space over geological time.",
    ),
    "bepicolombo": MissionInfo(
        id="bepicolombo",
        name="BepiColombo",
        agency="ESA / JAXA",
        launch_date="2018-10-20",
        mission_status="operational",
        primary_targets=["mercury", "venus"],
        instruments=[
            InstrumentInfo(id="MORE", name="Mercury Orbiter Radio science Experiment", instrument_type="radio_science",
                           measurement_targets=["gravity", "occultation"],
                           description="High-precision radio science investigation during cruise flybys and Mercury orbit."),
            InstrumentInfo(id="MERTIS", name="Mercury Radiometer and Thermal Infrared Spectrometer", instrument_type="spectrometer",
                           measurement_targets=["surface", "thermal"],
                           description="Thermal infrared imaging spectrometer active during Venus flybys and Mercury science operations."),
            InstrumentInfo(id="PHEBUS", name="Probing of Hermean Exosphere By Ultraviolet Spectroscopy", instrument_type="spectrometer",
                           measurement_targets=["exosphere"],
                           description="UV spectrometer observing exospheric composition and emissions."),
        ],
        authoritative_archive="ESA Planetary Science Archive (PSA)",
        archive_url="https://archives.esac.esa.int/psa/",
        citation="Benkhoff, J., et al. (2010). BepiColombo: Comprehensive exploration of Mercury: Mission overview and science goals. PSS, 58(1), 2-20.",
        description="Joint European-Japanese mission to Mercury, performing multiple scientific flybys of Venus and Mercury on its cruise.",
    ),
    "galileo": MissionInfo(
        id="galileo",
        name="Galileo",
        agency="NASA / JPL",
        launch_date="1989-10-18",
        mission_status="completed",
        primary_targets=["jupiter", "venus"],
        instruments=[
            InstrumentInfo(id="RSS", name="Radio Science", instrument_type="radio_science",
                           measurement_targets=["neutral_atmosphere", "ionosphere"],
                           description="S/X-band radio occultation measurements of Jupiter and Galilean moon ionospheres and atmospheres."),
            InstrumentInfo(id="SSI", name="Solid State Imaging", instrument_type="camera",
                           measurement_targets=["clouds", "moons"],
                           description="First CCD camera to orbit an outer planet, capturing dynamic atmospheric features and volcanism on Io."),
        ],
        authoritative_archive="NASA PDS Atmospheres Node / Imaging Node",
        archive_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/catalog.htm#Jupiter",
        citation="Kliore, A. J., et al. (1997). The ionosphere of Europa from Galileo radio occultations. Science, 277(5324), 355-358.",
        description="Historic Jupiter orbiter that released an atmospheric probe and conducted first extensive radio occultations of Jovian moons.",
    ),
}


def get_body(body_id: str) -> Optional[BodyInfo]:
    """Retrieve planetary body metadata."""
    return BODIES.get(body_id.lower())


def get_mission(mission_id: str) -> Optional[MissionInfo]:
    """Retrieve mission metadata."""
    return MISSIONS.get(mission_id.lower())


def list_bodies() -> List[dict]:
    """List all supported planetary bodies."""
    return [
        {
            "id": b.id,
            "name": b.name,
            "category": b.category,
            "radius_km": b.radius_km,
            "surface_gravity": b.surface_gravity,
            "gas_constant_r": b.gas_constant_r,
            "reference_pressure_hpa": b.reference_pressure_hpa,
            "description": b.description,
            "supported_missions": b.supported_missions,
        }
        for b in BODIES.values()
    ]


def list_missions() -> List[dict]:
    """List all supported spacecraft missions."""
    return [
        {
            "id": m.id,
            "name": m.name,
            "agency": m.agency,
            "launch_date": m.launch_date,
            "mission_status": m.mission_status,
            "primary_targets": m.primary_targets,
            "authoritative_archive": m.authoritative_archive,
            "archive_url": m.archive_url,
            "citation": m.citation,
            "description": m.description,
            "instruments": [
                {
                    "id": i.id,
                    "name": i.name,
                    "type": i.instrument_type,
                    "targets": i.measurement_targets,
                    "description": i.description,
                }
                for i in m.instruments
            ],
        }
        for m in MISSIONS.values()
    ]


def get_missions_for_body(body_id: str) -> List[dict]:
    """Return all missions that observed a specific body."""
    body = get_body(body_id)
    if not body:
        return []
    res = []
    for mid in body.supported_missions:
        m = get_mission(mid)
        if m:
            res.append({
                "id": m.id,
                "name": m.name,
                "agency": m.agency,
                "instruments": [i.name for i in m.instruments],
                "archive": m.authoritative_archive,
            })
    return res
