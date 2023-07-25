import random
import warnings
from typing import Any, Iterable, Optional, Union

import geopandas as gp
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from shapely.geometry import Point

from pam.activity import Activity, Leg
from pam.samplers.facility import FacilitySampler
from pam.utils import minutes_to_datetime as mtdt
from pam.variables import END_OF_DAY


def create_density_gdf(
    facility_zone: gp.GeoDataFrame,
    zone: gp.GeoDataFrame,
    activity: list[str],
    normalise: Optional[str] = None,
) -> gp.GeoDataFrame:
    """Calculate the spatial density of input activity.

    Args:
        facility_zone (gp.GeoDataFrame): Spatial join between facility and zone information.
        zone (gp.GeoDataFrame): zones information.
        activity (list[str]): a list of activities that are within facility data.
        normalise (Optional[str], optional): If given, normalise density against this variable. Defaults to None.

    Returns:
        gp.GeoDataFrame: measure of density of activities in each zone
    """
    if normalise is not None:
        density = (
            facility_zone.groupby([facility_zone.index, "activity", normalise])
            .agg({"id": "count"})
            .reset_index()
        )
        density.set_index(facility_zone.index.name, inplace=True)
        density = density[density["activity"].isin(activity)]
        density["density"] = density["id"] / density[normalise]
        total_density = density[~(density[normalise] == 0)]["density"].sum()
        density["density"] = density["density"] / total_density
    else:
        density = (
            facility_zone.groupby([facility_zone.index, "activity"])
            .agg({"id": "count"})
            .reset_index()
        )
        density.set_index(facility_zone.index.name, inplace=True)
        density = density[density["activity"].isin(activity)]
        density["density"] = density["id"] / density["id"].sum()

    # Convert back to geodataframe for merging.
    density = pd.merge(
        density, zone["geometry"], left_on=density.index, right_on=zone.index, how="left"
    )
    density.rename(columns={"key_0": facility_zone.index.name}, inplace=True)
    density = gp.GeoDataFrame(data=density, geometry="geometry")
    density.set_index(facility_zone.index.name, inplace=True)

    if np.isinf(density["density"]).sum() >= 1:
        warnings.warn("Your density gdf has infinite values")

    return density


class PivotDistributionSampler:
    """Defines a distribution, a sampler, and plots based on input values. The resulting distribution can be sampled
    for inputs required to build an agent plan (i.e, time of day, repetition of activities).
    """

    def __init__(self, bins: Iterable, pivots: dict, total=None):
        """Builds a dict distribution based on bins (i.e, hours) and pivots (i.e, hourly demand).

        Where the input pivot does not specify a value, values are estimated within the bin range by interpolation.

        Args:
            bins (Iterable): a range or dictionary of values
            pivots (dict): a dictionary of values associated with the bins.
            total (optional): Defaults to None.
        """
        self.demand = {}

        if bins[0] not in pivots:
            pivots[bins[0]] = 0
        if bins[-1] + 1 not in pivots:
            pivots[bins[-1] + 1] = 0

        pivot_keys = sorted(pivots.keys())

        for k in range(len(pivot_keys) - 1):
            ka = pivot_keys[k]
            kb = pivot_keys[k + 1]
            pivot_a = pivots[ka]
            pivot_b = pivots[kb]
            for i in bins:
                if ka <= i < kb:
                    self.demand[i] = self._interpolate(i, ka, pivot_a, kb, pivot_b)
                else:
                    continue

        if total is not None:
            dist_sum = sum(self.demand.values())
            for i in bins:
                self.demand[i] = (self.demand[i] / dist_sum) * total

    @staticmethod
    def _interpolate(i, ai, a, bi, b):
        "input values to build distribution between values a and ai."
        return a + (i - ai) * (b - a) / (bi - ai)

    def plot(self, plot_title, x_label, y_label):
        """Plots distribution to validate the distribution aligns with expected hourly demand."""
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar(list(self.demand.keys()), list(self.demand.values()))
        ax.plot(list(self.demand.keys()), list(self.demand.values()), c="orange")
        ax.set_title(plot_title)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)

        return fig

    def sample(self):
        return random.choices(list(self.demand.keys()), list(self.demand.values()), k=1)[0]


class FrequencySampler:
    """Object for initiating and sampling from frequency weighted distributing.
    This object includes three samplers: a single sample, multiple samples, or sample based on a threshold value
    (requires a threshold matrix).
    """

    def __init__(
        self,
        dist: Union[Iterable, pd.DataFrame],
        freq: Optional[Union[str, Iterable]] = None,
        threshold_matrix: Optional[pd.DataFrame] = None,
        threshold_value: Optional[Union[int, float]] = None,
    ) -> None:
        """

        Args:
            dist (Union[Iterable, pd.DataFrame]):
                Input distribution. If a DataFrame is given, the index will be used.
            freq (Optional[Union[str, Iterable]], optional):
                If given, weighting for input items, either as an iterable or a reference to a column of `dist` (which then must be a DataFrame).
                Defaults to None.
            threshold_matrix (Optional[pd.DataFrame], optional):
                A dataframe that will be reduced based on a specified threshold_value. Defaults to None.
            threshold_value (Optional[Union[int, float]], optional):
                A value to filter the threshold_matrix. This is the maximum allowed value. Defaults to None.
        """
        self.distribution = dist
        self.frequency = freq
        self.threshold_matrix = threshold_matrix
        self.threshold_value = threshold_value

    def sample(self) -> Any:
        """

        Returns:
            Any: Single object sampled from distribution

        """
        return random.choices(self.distribution, weights=self.frequency, k=1)[0]

    def samples(self, n: int = 1) -> list:
        """

        Args:
          n (int, optional): number of samples to be returned. Defaults to 1.

        Returns:
          list: objects sampled from distribution

        """
        return random.choices(self.distribution, weights=self.frequency, k=n)

    def threshold_sample(self):
        """Returns a sampler of a distribution that has been reduced based on a threshold value."""
        d_list = self.threshold_matrix
        d_list = d_list[d_list <= self.threshold_value].index
        d_threshold = self.distribution[self.distribution.index.isin(d_list)]

        if len(d_threshold) == 0:
            warnings.warn("No destinations within this threshold value, change threshold")
            return None
        else:
            return random.choices(
                list(d_threshold.index), weights=list(d_threshold[self.frequency]), k=1
            )[0]


class ActivityDuration:
    """Object to estimate the distance, journey time, and stop time of activities.
    The last function activity_duration combines these three functions to output parameters that help build tour plans.
    """

    def model_distance(self, o, d, scale=1.4):
        """Models distance between two shapely points."""
        return o.distance(d) * scale

    def model_journey_time(self, distance: Union[float, int], speed: float = 50000 / 3600) -> float:
        """

        Args:
          distance (Union[float, int]): Distance in metres.
          speed (float, optional): Speed in metres/second. Defaults to 50000 / 3600 (50km/hr).

        Returns:
          float: Modelled journey time.

        """
        return distance / speed

    def model_stop_time(self, time: int, maxi: int = 3600, mini: int = 600) -> int:
        """Returns a duration that is between the minimum amount of seconds, an input journey time, or maximum time.

        Args:
          time (int): Time in seconds.
          maxi (int, optional): maximum time for a journey. Defaults to 3600.
          mini (int, optional): minimum time for a journey. Defaults to 600.

        Returns:
          int: maximum value between minimum time or the minimum of journey time and maximum time.

        """
        return max([mini, min([time, maxi])])

    def model_activity_duration(
        self,
        o_loc: Point,
        d_loc: Point,
        end_tm: int,
        speed: Union[int, float] = 50000 / 3600,
        maxi: int = 3600,
        mini: int = 600,
    ) -> tuple[int, int, int]:
        """Returns estimated Activity duration.

        Duration is a combination of previous three functions to return parameters for next activity in Plan.

        Args:
          o_loc (shapely.Point): origin facility.
          d_loc (shapely.Point): destination facility.
          end_tm (int): most recent end time of previous leg.
          speed (Union[int, float], optional): Speed of vehicle in metres/second. Defaults to 50000 / 3600 (50km/hr).
          maxi (int, optional): maximum stop time in seconds. Defaults to 3600.
          mini (int, optional): minimum stop time in seconds. Defaults to 600.

        Returns:
          tuple[int, int, int]: (stop_duration, start_tm, end_tm) for new activity.

        """
        trip_distance = self.model_distance(o_loc, d_loc)
        trip_duration = self.model_journey_time(trip_distance, speed)
        stop_duration = self.model_stop_time(trip_duration, maxi, mini)

        start_tm = end_tm
        end_tm = end_tm + int(trip_duration / 60)

        return stop_duration, start_tm, end_tm


class TourPlanner:
    """Object to plan the tour of the agent. This includes sequencing the stops and adding the activity and leg via an apply method."""

    def __init__(
        self,
        stops: int,
        hour: int,
        minute: int,
        o_zone: str,
        d_dist: Union[Iterable, pd.DataFrame],
        d_freq: Union[str, Iterable],
        facility_sampler: FacilitySampler,
        activity_params: dict[str, str],
        threshold_matrix=None,
        threshold_value=None,
    ):
        """
        Args:
            stops (int): # of stops.
            hour (int): input of sampled hour.
            minute (int): input of sampled minute.
            o_zone (str): origin zone.
            d_dist (Union[Iterable, pd.DataFrame]): distribution of destination zones.
            d_freq (Union[str, Iterable]): frequency value to sample of destination distribution.
            facility_sampler (FacilitySampler):
            activity_params (dict[str, str]): dictionary of str of origin activity (str) and destination activity (str).
            threshold_matrix (optional): dataframe that will be reduced based on threshold value. Defaults to None.
            threshold_value (optional): maximum threshold value allowed between origin and destination in threshold_matrix. Defaults to None.
        """
        self.stops = stops
        self.hour = hour
        self.minute = minute
        self.o_zone = o_zone
        self.threshold_matrix = threshold_matrix
        self.d_dist = d_dist
        self.d_freq = d_freq
        self.threshold_value = threshold_value
        self.facility_sampler = facility_sampler
        self.o_activity = activity_params["o_activity"]
        self.d_activity = activity_params["d_activity"]

    def sequence_stops(self) -> tuple[list, list, list]:
        """Creates a sequence for a number of stops. Sequence is determined by distance from origin.

        TODO - Method to sequence stops with different logic (i.e, minimise distance between stops).

        Returns:
          tuple[list, list, list]: (o_loc, d_zones, d_locs).

        """
        o_loc = self.facility_sampler.sample(self.o_zone, self.o_activity)

        d_seq = []

        for j in range(self.stops):
            # If threshold matrix is none, sample a random d_zone, else select a d_zone within threshold value
            if self.threshold_matrix is None:
                d_zone = FrequencySampler(self.d_dist.index, self.d_dist[self.d_freq]).sample()
            else:
                d_zone = FrequencySampler(
                    dist=self.d_dist,
                    freq=self.d_freq,
                    threshold_matrix=self.threshold_matrix.loc[self.o_zone],
                    threshold_value=self.threshold_value,
                ).threshold_sample()
            # once d_zone is selected, select a specific point location for d_activity
            d_facility = self.facility_sampler.sample(d_zone, self.d_activity)

            # append to a dictionary to sequence destinations
            d_seq.append(
                {
                    "stops": j,
                    "destination_zone": d_zone,
                    "destination_facility": d_facility,
                    "distance": ActivityDuration().model_distance(o_loc, d_facility),
                }
            )

        # sort distance: furthest facility to closest facility to origin facility. The final stop should be closest to origin.
        d_seq = sorted(d_seq, key=lambda item: item.get("distance"), reverse=True)
        d_zones = [item.get("destination_zone") for item in d_seq]
        d_locs = [item.get("destination_facility") for item in d_seq]

        return o_loc, d_zones, d_locs

    def add_tour_activity(
        self, agent: str, k: Iterable, zone: str, loc: Point, activity_type: str, time_params: dict
    ) -> int:
        """Add activity to tour plan. This will add an activity to the agent plan after each leg within the tour.

        Args:
          agent (str): agent for which the activity will be added to Plan
          k (int): when used in a for loop, k populates the next sequence value
          zone (str): zone where activity takes place
          loc (shapely.Point): facility location where activity takes place
          activity_type (str): this function has specific logic for 'return_origin'
          time_params (dict[str, str]): dictionary of time_params that may be time samplers or times of previous journeys

        Returns:
          int: end_tm of activity.

        """
        if activity_type == self.o_activity:
            start_tm = 0
            end_tm = (time_params["hour"] * 60) + time_params["minute"]
            seq = 1
            act = activity_type
        elif activity_type == "return_origin":
            start_tm = time_params["start_tm"]  # end_tm
            end_tm = time_params["end_tm"]  # END_OF_DAY we'll let pam trim this to 24 hours later
            seq = k + 2
            act = self.o_activity
        else:
            start_tm = time_params["end_tm"]
            end_tm = time_params["end_tm"] + int(time_params["stop_duration"] / 60)
            seq = k + 2
            act = activity_type

        # Activity plan requires mtdt format, but int format needs to passed for other functions to calculate new start time.
        # END_OF_DAY is already in mtdt format, adding an exception to keep set mtdt format when not END_OF_DAY.
        if end_tm is not END_OF_DAY:
            end_tm_mtdt = mtdt(end_tm)
        else:
            end_tm_mtdt = end_tm

        agent.add(
            Activity(
                seq=seq,
                act=act,
                area=zone,
                loc=loc,
                start_time=mtdt(start_tm),
                end_time=end_tm_mtdt,
            )
        )

        return end_tm

    def add_tour_leg(
        self,
        agent: str,
        k: Iterable,
        o_zone: str,
        o_loc: Point,
        d_zone: str,
        d_loc: Point,
        start_tm: int,
        end_tm: int,
    ) -> int:
        """Leg to Next Activity within the tour. This adds a leg to the agent plan after each activity is complete within the tour.

        Args:
          agent (str): agent for which the leg will be added to Plan
          k (Iterable): when used in a for loop, k populates the next sequence value
          o_zone (str): origin zone of leg
          o_loc (shapely.point): origin facility of leg
          d_zone (str): destination zone of leg
          d_loc (shapely.point): destination facility of leg
          start_tm (int): obtained from ActivityDuration object
          end_tm (int): obtained from ActivityDuration object

        Returns:
          int: new end_tm after leg is added to plan.

        """
        agent.add(
            Leg(
                seq=k + 1,
                mode="car",
                start_area=o_zone,
                end_area=d_zone,
                start_loc=o_loc,
                end_loc=d_loc,
                start_time=mtdt(start_tm),
                end_time=mtdt(end_tm),
            )
        )

        return end_tm

    def add_return_origin(
        self, agent: str, k: Iterable, o_loc: Point, d_zone: str, d_loc: Point, end_tm: int
    ) -> int:
        """The agent returns to their origin activity, from their most recent stop to the origin location.

        Args:
          agent (str): agent for which the leg & activity will be added to Plan
          k (Iterable): when used in a for loop, k populates the next sequence valuey
          o_loc (shapely.Point): origin facility of leg & activity
          d_zone (str): destination zone of leg & activity
          d_loc (shapely.Point): destination facility of leg & activity
          end_tm (int): obtained from ActivityDuration object

        Returns:
          int: end_tm after returning to origin.

        """
        trip_distance = ActivityDuration().model_distance(o_loc, d_loc)
        trip_duration = ActivityDuration().model_journey_time(trip_distance)

        start_tm = end_tm
        end_tm = end_tm + int(trip_duration / 60)

        end_tm = self.add_tour_leg(
            agent=agent,
            k=k,
            o_zone=d_zone,
            o_loc=d_loc,
            d_zone=self.o_zone,
            d_loc=o_loc,
            start_tm=start_tm,
            end_tm=end_tm,
        )

        time_params = {"start_tm": end_tm, "end_tm": END_OF_DAY}
        end_tm = self.add_tour_activity(
            agent=agent,
            k=k,
            zone=self.o_zone,
            loc=o_loc,
            activity_type="return_origin",
            time_params=time_params,
        )

        return end_tm

    def apply(self, agent: str, o_loc: Point, d_zones: list, d_locs: list) -> None:
        """Apply the above functions to the agent to build a plan.

        Args:
          agent (str): agent to build a plan fory
          o_loc (shapely.Point): origin facility of leg & activity
          d_zones (list): destination zones of leg & activity
          d_locs (list): destination facilities of leg & activity.

        """
        time_params = {"hour": self.hour, "minute": self.minute}
        end_tm = self.add_tour_activity(
            agent=agent,
            k=1,
            zone=self.o_zone,
            loc=o_loc,
            activity_type=self.o_activity,
            time_params=time_params,
        )

        for k in range(self.stops):
            stop_duration, start_tm, end_tm = ActivityDuration().model_activity_duration(
                o_loc, d_locs[k], end_tm
            )
            if (mtdt(end_tm) >= END_OF_DAY) | (
                mtdt(end_tm + int(stop_duration / 60)) >= END_OF_DAY
            ):
                break
            elif k == 0:
                end_tm = self.add_tour_leg(
                    agent=agent,
                    k=k,
                    o_zone=self.o_zone,
                    o_loc=o_loc,
                    d_zone=d_zones[k],
                    d_loc=d_locs[k],
                    start_tm=start_tm,
                    end_tm=end_tm,
                )

                time_params = {"end_tm": end_tm, "stop_duration": stop_duration}
                end_tm = self.add_tour_activity(
                    agent=agent,
                    k=k,
                    zone=d_zones[k],
                    loc=d_locs[k],
                    activity_type=self.d_activity,
                    time_params=time_params,
                )
            else:
                end_tm = self.add_tour_leg(
                    agent=agent,
                    k=k,
                    o_zone=d_zones[k - 1],
                    o_loc=d_locs[k - 1],
                    d_zone=d_zones[k],
                    d_loc=d_locs[k],
                    start_tm=start_tm,
                    end_tm=end_tm,
                )

                time_params = {"end_tm": end_tm, "stop_duration": stop_duration}
                end_tm = self.add_tour_activity(
                    agent=agent,
                    k=k,
                    zone=d_zones[k],
                    loc=d_locs[k],
                    activity_type=self.d_activity,
                    time_params=time_params,
                )

        end_tm = self.add_return_origin(
            agent=agent,
            k=self.stops,
            o_loc=o_loc,
            d_zone=d_zones[self.stops - 1],
            d_loc=d_locs[self.stops - 1],
            end_tm=end_tm,
        )


class ValidateTourOD:
    """Object to build a dataframe that produces both spatial and statistical plots to validate the tour origin and
    destinations align with input data.
    """

    def __init__(
        self,
        trips: pd.DataFrame,
        zone: gp.GeoDataFrame,
        o_dist: pd.DataFrame,
        d_dist: pd.DataFrame,
        o_activity: str,
        d_activity: str,
        o_freq: str,
        d_freq: str,
    ):
        """Create a dataframe that counts the number of origin and destination activities.

        Merge this against the density information from the input origin and destination samplers.

        Args:
            trips (pd.DataFrame): the legs.csv output after building population.
            zone (gp.GeoDataFrame):
            o_dist (pd.DataFrame): sampler containing origin distributions to be sampled.
            d_dist (pd.DataFrame): sampler containing destination distributions to be sampled.
            o_activity (str): activity utilised within o_dist.
            d_activity (str): activity utilised within d_dist.
            o_freq (str): destination frequency that is used to sample origin distributions.
            d_freq (str): destination frequency that is used to sample destination distributions.
        """
        # Create a dataframe to plot od trips and compare against facility density and flows density.
        df_trips_o = (
            trips[trips["origin activity"] == o_activity]
            .groupby(["ozone"])
            .agg({"pid": "count"})
            .reset_index()
        )
        df_trips_o.rename(columns={"pid": "origin_trips"}, inplace=True)
        df_trips_o.set_index("ozone", inplace=True)

        df_trips_d = (
            trips[trips["destination activity"] == d_activity]
            .groupby(["dzone"])
            .agg({"pid": "count"})
            .reset_index()
        )
        df_trips_d.rename(columns={"pid": "destination_trips"}, inplace=True)
        df_trips_d.set_index("dzone", inplace=True)

        self.od_density = zone.copy()

        # Merge in trips information
        self.od_density = pd.merge(
            self.od_density,
            df_trips_o,
            left_on=self.od_density.index,
            right_on=df_trips_o.index,
            how="left",
        )
        self.od_density = pd.merge(
            self.od_density, df_trips_d, left_on="key_0", right_on=df_trips_d.index, how="left"
        )

        # Merge in density information
        o_density = o_dist.reset_index()
        o_density = o_density.groupby(o_dist.index).agg({o_freq: "sum"})
        d_density = d_dist.reset_index()
        d_density = d_density.groupby(d_dist.index).agg({d_freq: "sum"})

        self.od_density[f"{o_activity}_density"] = self.od_density.key_0.map(o_density[o_freq])
        self.od_density[f"{d_activity}_density"] = self.od_density.key_0.map(d_density[d_freq])

        self.od_density.rename(columns={"key_0": zone.index.name}, inplace=True)
        self.od_density.set_index(zone.index.name, inplace=True)

        # Add in features for analysis
        self.od_density = self.od_density.fillna(0)
        self.od_density["origin_trip_density"] = (
            self.od_density.origin_trips / self.od_density.origin_trips.sum()
        )
        self.od_density["destination_trip_density"] = (
            self.od_density.destination_trips / self.od_density.destination_trips.sum()
        )
        self.od_density["origin_diff"] = (
            self.od_density["origin_trip_density"] - self.od_density[f"{o_activity}_density"]
        )
        self.od_density["destination_diff"] = (
            self.od_density["destination_trip_density"] - self.od_density[f"{d_activity}_density"]
        )

    def plot_validate_spatial_density(
        self,
        title_1: str,
        title_2: str,
        density_metric: str,
        density_trips: str,
        cmap: str = "coolwarm",
    ) -> plt.Figure:
        """Creates a spatial plot between input densities and resulting trips to validate trips spatially align with input densities.

        Args:
          title_1 (str): Input densities plot title.
          title_2 (str): Resulting trips plot title.
          density_metric (str): the measure for density output from the above dataframe, in the format of 'activity_density'
          density_trips (str): the measure of trips that require validation, either 'origin_trips' or 'destination_trips'.
          cmap (str): Defaults to "coolwarm".

        Returns:
            plt.Figure:
        """
        fig, ax = plt.subplots(1, 2, figsize=(20, 10))

        self.od_density.plot(density_metric, ax=ax[0], cmap=cmap)
        ax[0].axis("off")
        ax[0].set_title(title_1)

        self.od_density.plot(density_trips, ax=ax[1], cmap=cmap)
        ax[1].axis("off")
        ax[1].set_title(title_2)

        im = plt.gca().get_children()[0]
        cax = fig.add_axes([1, 0.2, 0.03, 0.6])
        plt.colorbar(im, cax=cax)

        return fig

    def plot_compare_density(
        self, title_1: str, title_2: str, o_activity: str, d_activity: str
    ) -> plt.Figure:
        """Compares density of input origin/destination activities and trips. As density of locations increases, so should trips.

        Args:
          title_1 (str): input for plot origin title name.
          title_2 (str): input for plot destination title name.
          o_activity (str): activity used to measure density of origin locations.
          d_activity (str): activity used to measure density of destination locations.

        Returns:
            plt.Figure:
        """
        fig, ax = plt.subplots(1, 2, figsize=(15, 7))

        m1, b1 = np.polyfit(self.od_density[o_activity], self.od_density.origin_trip_density, 1)
        m2, b2 = np.polyfit(
            self.od_density[d_activity], self.od_density.destination_trip_density, 1
        )

        ax[0].scatter(x=o_activity, y="origin_trip_density", data=self.od_density)
        ax[0].plot(
            self.od_density[o_activity],
            (m1 * self.od_density[o_activity] + b1),
            label="y = {:.2f} + {:.2f}*x".format(m1, b1),
        )
        ax[0].legend(loc="lower right")
        ax[0].set_title(title_1)

        ax[1].scatter(x=d_activity, y="destination_trip_density", data=self.od_density)
        ax[1].plot(
            self.od_density[o_activity],
            (m2 * self.od_density[o_activity] + b2),
            label="y = {:.2f} + {:.2f}*x".format(m2, b2),
        )
        ax[1].legend(loc="lower right")
        ax[1].set_title(title_2)

        return fig

    def plot_density_difference(
        self, title_1: str, title_2: str, cmap: str = "coolwarm"
    ) -> plt.Figure:
        """Creates a spatial plot of the difference between input and output densities.

        Args:
          title_1 (str): input for plot origin title name.
          title_2 (str): input for plot destination title name.
          cmap (str, optional): Defaults to "coolwarm"

        Returns:
            plt.Figure:
        """
        fig, ax = plt.subplots(1, 2, figsize=(20, 10))

        self.od_density.plot("origin_diff", ax=ax[0], cmap=cmap)
        ax[0].axis("off")
        ax[0].set_title(title_1)

        self.od_density.plot("destination_diff", ax=ax[1], cmap=cmap)
        ax[1].axis("off")
        ax[1].set_title(title_2)

        im = plt.gca().get_children()[0]
        cax = fig.add_axes([1, 0.2, 0.03, 0.6])
        plt.colorbar(im, cax=cax)

        return fig