# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Robot library operations exercised against the installed musl environment."""
import platform

import coal
import eigenpy
import numpy as np
import pinocchio as pin


def test_versions():
    assert platform.python_version_tuple()[:2] == ('3', '13')
    assert np.__version__ == '2.3.5'
    assert pin.__version__ == '3.9.0'
    assert eigenpy.__version__ == '3.12.0'
    assert coal.__version__ == '3.0.2'


def test_forward_and_inverse_dynamics():
    model = pin.buildSampleModelManipulator()
    data = model.createData()
    q = pin.neutral(model)
    v = np.linspace(-0.1, 0.1, model.nv)
    acceleration = np.linspace(0.1, 0.3, model.nv)
    torque = pin.rnea(model, data, q, v, acceleration).copy()
    recovered = pin.aba(model, data, q, v, torque).copy()
    np.testing.assert_allclose(recovered, acceleration, atol=1e-10)
    mass = pin.crba(model, data, q)
    assert np.linalg.eigvalsh(mass).min() > 0


def test_kinematics_and_jacobian():
    model = pin.buildSampleModelManipulator()
    data = model.createData()
    q = pin.neutral(model)
    joint = model.njoints - 1
    jac = pin.computeJointJacobian(model, data, q, joint).copy()
    pin.forwardKinematics(model, data, q)
    before = data.oMi[joint].copy()
    velocity = np.linspace(0.1, 0.5, model.nv)
    epsilon = 1e-7
    pin.forwardKinematics(model, data, pin.integrate(model, q, epsilon * velocity))
    difference = pin.log6(before.inverse() * data.oMi[joint]).vector / epsilon
    np.testing.assert_allclose(difference, jac @ velocity, atol=1e-6)


def test_coal_collision_and_distance():
    sphere = coal.Sphere(1.0)
    first = coal.Transform3s.Identity()
    overlap = coal.Transform3s(np.eye(3), np.array([1.0, 0, 0]))
    separate = coal.Transform3s(np.eye(3), np.array([3.0, 0, 0]))
    request = coal.CollisionRequest()
    assert coal.collide(sphere, first, sphere, overlap, request, coal.CollisionResult()) > 0
    assert coal.collide(sphere, first, sphere, separate, request, coal.CollisionResult()) == 0
    distance = coal.distance(sphere, first, sphere, separate, coal.DistanceRequest(), coal.DistanceResult())
    np.testing.assert_allclose(distance, 1.0, atol=1e-10)


def test_urdf_and_pinocchio_collision(tmp_path):
    urdf = tmp_path / 'sliding.urdf'
    urdf.write_text('''<robot name="sliding">
      <link name="base"><collision><geometry><box size="1 1 1"/></geometry></collision></link>
      <link name="moving">
        <inertial><mass value="1"/><inertia ixx="1" iyy="1" izz="1" ixy="0" ixz="0" iyz="0"/></inertial>
        <collision><geometry><box size="1 1 1"/></geometry></collision>
      </link>
      <joint name="slide" type="prismatic"><parent link="base"/><child link="moving"/>
        <axis xyz="1 0 0"/><limit lower="0" upper="4" effort="100" velocity="10"/>
      </joint>
    </robot>''')
    model, geometry, _ = pin.buildModelsFromUrdf(str(urdf))
    assert model.nq == 1 and geometry.ngeoms == 2
    geometry.addAllCollisionPairs()
    data = model.createData()
    geometry_data = pin.GeometryData(geometry)
    assert pin.computeCollisions(model, data, geometry, geometry_data, np.array([0.0]), False)
    assert not pin.computeCollisions(model, data, geometry, geometry_data, np.array([3.0]), False)


def test_assimp_mesh_loading(tmp_path):
    mesh = tmp_path / 'triangle.obj'
    mesh.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    loaded = coal.MeshLoader().load(str(mesh))
    assert loaded.num_tris == 1
