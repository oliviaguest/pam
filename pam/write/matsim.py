import os
from datetime import datetime
import logging
from lxml import etree as et
from typing import Optional, Set

from pam.activity import Plan, Activity, Leg
from pam.vehicle import Vehicle, ElectricVehicle, VehicleType
from pam.utils import datetime_to_matsim_time as dttm
from pam.utils import timedelta_to_matsim_time as tdtm
from pam.utils import create_local_dir, is_gzip, DEFAULT_GZIP_COMPRESSION


def write_matsim(
        population,
        plans_path : str,
        vehicles_dir : Optional[str] = None,
        version : int = 12, # TODO remove parameter
        comment : Optional[str] = None,
        household_key : Optional[str] = 'hid',
        keep_non_selected : bool = False,
        coordinate_reference_system: str = None,
    ) -> None:
    """
    Write a core population to matsim population v6 xml format.
    Note that this requires activity locs to be set (shapely.geometry.Point).
    TODO add support for PathLib?

    :param population: core.Population, population to be writen to disk
    :param plans_path: str, output path (.xml or .xml.gz)
    :param vehicles_dir: {str,None}, default None, path to output directory for vehicle files
    :param version: int {12}, legacy parameter, does not have an effect
    :param comment: {str, None}, default None, optionally add a comment string to the xml outputs
    :param household_key: {str,None}, optionally add household id to person attributes, default 'hid'
    :param keep_non_selected: bool, default False
    :param coordinate_reference_system: {str, None}, default None, optionally add CRS attribute to xml outputs
    :return: None
    """
    write_matsim_population_v6(
        population=population,
        path=plans_path,
        comment=comment,
        household_key=household_key,
        keep_non_selected=keep_non_selected,
        coordinate_reference_system = coordinate_reference_system,
    )
    
    # write vehicles
    if population.has_vehicles:
        logging.info('Population includes vehicles')
        if vehicles_dir is None:
            raise UserWarning("Please provide a vehicles_dir to write vehicle files")
        else:
            logging.info(f'Saving vehicles to {vehicles_dir}')
            write_vehicles(output_dir=vehicles_dir, population=population)


def write_matsim_population_v6(
    population,
    path : str,
    household_key : Optional[str] = 'hid',
    comment : Optional[str] = None,
    keep_non_selected: bool = False,
    coordinate_reference_system: str = None,
    ) -> None:
    """
    Write matsim population v6 xml (persons plans and attributes combined).
    :param population: core.Population, population to be writen to disk
    :param path: str, output path (.xml or .xml.gz)
    :param comment: {str, None}, default None, optionally add a comment string to the xml outputs
    :param household_key: {str, None}, default 'hid'
    :param keep_non_selected: bool, default False
    """

    create_local_dir(os.path.dirname(path))
    
    compression = DEFAULT_GZIP_COMPRESSION if is_gzip(path) else 0
    with et.xmlfile(path, encoding="utf-8", compression=compression) as xf:
        xf.write_declaration()
        xf.write_doctype(
            '<!DOCTYPE population SYSTEM "http://matsim.org/files/dtd/population_v6.dtd">'
        )

        with xf.element("population"):
            # Add some useful comments
            if comment:
                xf.write(et.Comment(comment), pretty_print=True)
            xf.write(et.Comment(f"Created {datetime.today()}"), pretty_print=True)

            # see MATSim's ProjectionUtils.getCRS
            if coordinate_reference_system is not None:
                attributes_element = et.Element('attributes')
                crs_attribute = et.SubElement(attributes_element, 'attribute', {'class': 'java.lang.String', 'name': 'coordinateReferenceSystem'})
                crs_attribute.text = str(coordinate_reference_system)
                xf.write(attributes_element, pretty_print=True)

            for hid, household in population:
                for pid, person in household:
                    if household_key is not None:
                        person.attributes[
                            household_key
                        ] = hid  # force add hid as an attribute
                    e = create_person_element(pid, person, keep_non_selected)
                    xf.write(e, pretty_print=True)


def create_person_element(pid, person, keep_non_selected: bool = False):
    person_xml = et.Element('person', {'id': str(pid)})

    attributes = et.SubElement(person_xml, 'attributes', {})
    for k, v in person.attributes.items():
        if k == "vehicles":  # todo make something more robust for future 'special' classes
            attribute = et.SubElement(
                attributes, 'attribute', {'class': 'org.matsim.vehicles.PersonVehicles', 'name': str(k)}
                )
            attribute.text = str(v)
        else:
            add_attribute(attributes, k, v)

    write_plan(
        person_xml,
        person.plan,
        selected=True,
    )
    if keep_non_selected:
        for plan in person.plans_non_selected:
            write_plan(
                person_xml,
                plan,
                selected=False,
            )
    return person_xml


def write_plan(
    person_xml: et.SubElement,
    plan: Plan,
    selected: Optional[bool] = None,
):
    plan_attributes = {}
    if selected is not None:
        plan_attributes['selected'] = {True:'yes', False:'no'}[selected]
    if plan.score is not None:
        plan_attributes['score'] = str(plan.score)

    plan_xml = et.SubElement(person_xml, 'plan', plan_attributes)
    for component in plan:
        if isinstance(component, Activity):
            component.validate_matsim()
            act_data = {
                'type': component.act,
            }
            if component.start_time is not None:
                act_data['start_time'] = dttm(component.start_time)
            if component.end_time is not None:
                act_data['end_time'] = dttm(component.end_time)
            if component.location.link is not None:
                act_data['link'] = str(component.location.link)
            if component.location.x is not None:
                act_data['x'] = str(component.location.x)
            if component.location.y is not None:
                act_data['y'] = str(component.location.y)
            et.SubElement(plan_xml, 'activity', act_data)

        if isinstance(component, Leg):
            leg = et.SubElement(plan_xml, 'leg', {
                'mode': component.mode,
                'trav_time': tdtm(component.duration)})

            if component.attributes:
                attributes = et.SubElement(leg, 'attributes')
                for k, v in component.attributes.items():
                    if k == 'enterVehicleTime':  # todo make something more robust for future 'special' classes
                        attribute = et.SubElement(
                        attributes, 'attribute', {'class': 'java.lang.Double', 'name': str(k)}
                        )
                        attribute.text = str(v)
                    else:
                        add_attribute(attributes, k, v)

            if component.route.exists:
                leg.append(component.route.xml)


def add_attribute(attributes, k, v):
    if type(v) == bool:
        attribute = et.SubElement(attributes, 'attribute', {'class': 'java.lang.Boolean', 'name': str(k)})
    elif type(v) == int:
        attribute = et.SubElement(attributes, 'attribute', {'class': 'java.lang.Integer', 'name': str(k)})
    elif type(v) == float:
        attribute = et.SubElement(attributes, 'attribute', {'class': 'java.lang.Double', 'name': str(k)})
    else:
        attribute = et.SubElement(attributes, 'attribute', {'class': 'java.lang.String', 'name': str(k)})
    attribute.text = str(v)


def object_attributes_dtd():
    dtd_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..", "fixtures", "dtd", "objectattributes_v1.dtd"
            )
        )
    return et.DTD(dtd_path)


def population_v6_dtd():
    dtd_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..", "fixtures", "dtd", "population_v6.dtd"
            )
        )
    return et.DTD(dtd_path)


def write_vehicles(output_dir,
                   population,
                   all_vehicles_filename="all_vehicles.xml",
                   electric_vehicles_filename="electric_vehicles.xml"):
    """
    Writes:
        - all_vehicles file following format https://www.matsim.org/files/dtd/vehicleDefinitions_v2.0.xsd
        - electric_vehicles file following format https://www.matsim.org/files/dtd/electric_vehicles_v1.dtd
    given a population in which Persons have been assigned vehicles.
    :param output_dir: output directory for all_vehicles file
    :param population: pam.core.Population
    :param all_vehicles_filename: name of output all vehicles file, defaults to 'all_vehicles.xml`
    :param electric_vehicles_filename: name of output electric vehicles file, defaults to 'electric_vehicles.xml`
    :return:
    """
    if population.has_vehicles:
        if population.has_uniquely_indexed_vehicle_types:
            write_all_vehicles(
                output_dir,
                vehicles=population.vehicles(),
                vehicle_types=population.vehicle_types(),
                file_name=all_vehicles_filename)
            if population.has_electric_vehicles:
                logging.info('Population includes electric vehicles')
                electric_vehicles = set(population.electric_vehicles())
                write_electric_vehicles(
                    output_dir,
                    vehicles=electric_vehicles,
                    file_name=electric_vehicles_filename
                )
                electric_vehicle_charger_types = population.electric_vehicle_charger_types()
                logging.info(f'Found {len(electric_vehicles)} electric vehicles '
                             f'with unique charger types: {electric_vehicle_charger_types}. '
                             "Ensure you generate a chargers xml file: https://www.matsim.org/files/dtd/chargers_v1.dtd "
                             "if you're running a simulation using org.matsim.contrib.ev")
            else:
                logging.info('Provided population does not have electric vehicles')
        else:
            logging.warning('The vehicle types in provided population do not have unique indices. Current Vehicle '
                            f'Type IDs: {[vt.id for vt in population.vehicle_types()]}')
    else:
        logging.warning('Provided population does not have vehicles')


def write_all_vehicles(
        output_dir,
        vehicles: Set[Vehicle],
        vehicle_types: Set[VehicleType],
        file_name="all_vehicles.xml"):
    """
    Writes all_vehicles file following format https://www.matsim.org/files/dtd/vehicleDefinitions_v2.0.xsd
    for MATSim
    :param output_dir: output directory for all_vehicles file
    :param vehicles: collection of vehicles to write
    :param vehicle_types: collection of vehicle types to write
    :param file_name: name of output file, defaults to 'all_vehicles.xml`
    :return: None
    """
    path = os.path.join(output_dir, file_name)
    logging.info(f'Writing all vehicles to {path}')

    with open(path, "wb") as f, et.xmlfile(f, encoding='utf-8') as xf:
        xf.write_declaration()
        vehicleDefinitions_attribs = {
            'xmlns': "http://www.matsim.org/files/dtd",
            'xmlns:xsi': "http://www.w3.org/2001/XMLSchema-instance",
            'xsi:schemaLocation': "http://www.matsim.org/files/dtd "
                                  "http://www.matsim.org/files/dtd/vehicleDefinitions_v2.0.xsd"}
        with xf.element("vehicleDefinitions", vehicleDefinitions_attribs):
            for vehicle_type in set(vehicle_types):
                vehicle_type.to_xml(xf)
            vehicles = list(vehicles)
            vehicles.sort()
            for vehicle in vehicles:
                vehicle.to_xml(xf)


def write_electric_vehicles(
        output_dir,
        vehicles: Set[ElectricVehicle],
        file_name="electric_vehicles.xml"):
    """
    Writes electric_vehicles file following format https://www.matsim.org/files/dtd/electric_vehicles_v1.dtd
    for MATSim
    :param output_dir: output directory for electric_vehicles file
    :param vehicles: collection of electric vehicles to write
    :param file_name: name of output file, defaults to 'electric_vehicles.xml`
    :return: None
    """
    path = os.path.join(output_dir, file_name)
    logging.info(f'Writing electric vehicles to {path}')

    with open(path, "wb") as f, et.xmlfile(f, encoding='utf-8') as xf:
        xf.write_declaration(
            doctype='<!DOCTYPE vehicles SYSTEM "http://matsim.org/files/dtd/electric_vehicles_v1.dtd">')
        with xf.element("vehicles"):
            vehicles = list(vehicles)
            vehicles.sort()
            for vehicle in vehicles:
                vehicle.to_e_xml(xf)
